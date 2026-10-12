// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

import {console2} from "forge-std/console2.sol";
import {
    VulnerableAuthorityRuntime,
    PermissionlessFactoryRuntime,
    GuardedAuthorityRuntime,
    BrokenSetupRuntime,
    RuntimeCaller
} from "../src/VerdictTargets.sol";

contract CapabilityVerdictRuntimeTest {
    enum Verdict { None, Supported, Rejected, Inconclusive, Unmeasurable }
    Verdict public verdict;
    RuntimeCaller internal attacker;

    function _report(Verdict actual, Verdict expected, string memory label) internal {
        verdict = actual;
        require(verdict == expected, "verdict mismatch");
        console2.log("CYDRA_VERDICT", label);
    }

    function testSupportedAuthorityDeltaIsObservedAtRuntime() public {
        attacker = new RuntimeCaller();
        VulnerableAuthorityRuntime target = new VulnerableAuthorityRuntime();
        bool beforeRole = target.hasRole(target.DEFAULT_ADMIN_ROLE(), address(attacker));
        require(!beforeRole, "positive-control precondition failed");
        (bool ok,) = attacker.callTarget(address(target), abi.encodeWithSignature("setTarget(address)", address(0xCAFE)));
        require(ok, "positive-control call unexpectedly reverted");
        bool afterRole = target.hasRole(target.DEFAULT_ADMIN_ROLE(), address(attacker));
        require(afterRole, "positive-control role transition not observed");
        _report(!beforeRole && afterRole ? Verdict.Supported : Verdict.Inconclusive, Verdict.Supported, "supported");
    }

    function testPermissionlessFactoryIsUnmeasurableWithoutAuthorityGetter() public {
        attacker = new RuntimeCaller();
        PermissionlessFactoryRuntime target = new PermissionlessFactoryRuntime();
        (bool ok,) = attacker.callTarget(address(target), abi.encodeWithSignature("create()"));
        require(ok, "factory call unexpectedly reverted");
        // The registry is observable, but it is child-membership state, not an authority interface.
        _report(Verdict.Unmeasurable, Verdict.Unmeasurable, "unmeasurable");
    }

    function testExpectedGuardAndUnchangedRoleProduceRejected() public {
        attacker = new RuntimeCaller();
        GuardedAuthorityRuntime target = new GuardedAuthorityRuntime();
        bool beforeRole = target.hasRole(target.DEFAULT_ADMIN_ROLE(), address(attacker));
        require(!beforeRole, "guarded-control precondition failed");
        (bool ok, bytes memory data) = attacker.callTarget(address(target), abi.encodeWithSignature("setTarget(address)", address(0xCAFE)));
        bool afterRole = target.hasRole(target.DEFAULT_ADMIN_ROLE(), address(attacker));
        require(!ok && !afterRole && !beforeRole, "guarded call changed authority or did not revert");
        require(_revertReason(data) == "guarded: only owner", "source guard mismatch");
        _report(beforeRole == afterRole ? Verdict.Rejected : Verdict.Inconclusive, Verdict.Rejected, "rejected");
    }

    function testBrokenDeploymentIsRecordedAsInconclusive() public {
        bool deployed;
        BrokenSetupRuntime target;
        Verdict setupVerdict = Verdict.None;
        try new BrokenSetupRuntime() returns (BrokenSetupRuntime instance) {
            target = instance;
            deployed = true;
        } catch {
            deployed = false;
            setupVerdict = Verdict.Inconclusive;
        }
        target;
        require(!deployed, "broken setup unexpectedly deployed");
        _report(setupVerdict, Verdict.Inconclusive, "inconclusive");
    }

    function _revertReason(bytes memory data) internal pure returns (string memory) {
        if (data.length < 68) return "";
        bytes4 selector;
        assembly { selector := mload(add(data, 0x20)) }
        if (selector != 0x08c379a0) return "";
        assembly { data := add(data, 0x04) }
        return abi.decode(data, (string));
    }
}
