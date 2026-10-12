// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

import {Test} from "forge-std/Test.sol";
import {TransferGuardFactory} from "src/guard/TransferGuardFactory.sol";
import {TransferGuard} from "src/guard/TransferGuard.sol";
import {AddressStatus, TokenMode} from "src/interfaces/guard/ITransferGuard.sol";

/// @notice Manual, source-pinned boundary test for the permissionless guard factory.
/// @dev This tests ownership/capability boundaries, not whether createTransferGuard is callable.
contract TransferGuardFactoryBoundaryTest is Test {
    address internal constant BEACON_OWNER = address(0xB001);
    address internal constant CREATOR = address(0xC001);
    address internal constant ALICE = address(0xA11CE);
    address internal constant BOB = address(0xB0B);
    address internal constant TOKEN = address(0x7001);
    address internal constant ACCOUNT = address(0xACCE);

    TransferGuardFactory internal factory;

    function setUp() public {
        factory = new TransferGuardFactory(BEACON_OWNER);
    }

    function _createGuard(address creator, address owner) internal returns (TransferGuard guard) {
        vm.prank(creator);
        guard = TransferGuard(factory.createTransferGuard(owner));
        assertTrue(factory.isTransferGuard(address(guard)), "new guard missing from factory registry");
    }

    function testCreatorCanAdministerGuardWhenCreatorIsItsDeclaredOwner() public {
        TransferGuard guard = _createGuard(CREATOR, CREATOR);

        vm.prank(CREATOR);
        guard.setTokenConfig(TOKEN, false, TokenMode.WHITELIST, false);

        (, TokenMode mode, bool checkCollateralAllowed) = guard.tokenConfig(TOKEN);
        assertEq(uint256(mode), uint256(TokenMode.WHITELIST));
        assertFalse(checkCollateralAllowed);
    }

    function testCreatorAndUnrelatedCallerCannotAdministerGuardOwnedByAliceButAliceCan() public {
        TransferGuard guard = _createGuard(CREATOR, ALICE);
        assertEq(guard.owner(), ALICE);

        vm.expectRevert();
        vm.prank(CREATOR);
        guard.setTokenConfig(TOKEN, false, TokenMode.WHITELIST, false);

        vm.expectRevert();
        vm.prank(BOB);
        guard.setTokenConfig(TOKEN, false, TokenMode.WHITELIST, false);

        vm.prank(ALICE);
        guard.setTokenConfig(TOKEN, false, TokenMode.WHITELIST, false);

        (, TokenMode mode,) = guard.tokenConfig(TOKEN);
        assertEq(uint256(mode), uint256(TokenMode.WHITELIST));
    }

    function testUnrelatedCallerCannotUpgradeBeaconButBeaconOwnerCan() public {
        address beacon = factory.TRANSFER_GUARD_BEACON();
        address nextImplementation = address(new TransferGuard());
        bytes memory payload = abi.encodeWithSignature("upgradeTo(address)", nextImplementation);

        (bool attackerSucceeded,) = beacon.call(payload);
        assertFalse(attackerSucceeded, "unrelated caller upgraded the beacon");

        vm.prank(BEACON_OWNER);
        (bool ownerSucceeded, bytes memory reason) = beacon.call(payload);
        assertTrue(ownerSucceeded, string.concat("beacon owner upgrade failed: ", _bytesToString(reason)));
    }

    function testCreatingAnotherGuardDoesNotChangeExistingGuardState() public {
        TransferGuard guardA = _createGuard(CREATOR, ALICE);

        vm.startPrank(ALICE);
        guardA.setTokenConfig(TOKEN, false, TokenMode.NATIVE_ONLY, true);
        guardA.setAddressStatus(ACCOUNT, AddressStatus.BLOCKLIST);
        vm.stopPrank();

        address ownerBefore = guardA.owner();
        (uint40 pausedBefore, TokenMode modeBefore, bool collateralBefore) = guardA.tokenConfig(TOKEN);
        AddressStatus statusBefore = guardA.addressStatus(ACCOUNT);

        TransferGuard guardB = _createGuard(BOB, BOB);

        assertTrue(address(guardA) != address(guardB), "factory returned same proxy twice");
        assertEq(guardA.owner(), ownerBefore);
        (uint40 pausedAfter, TokenMode modeAfter, bool collateralAfter) = guardA.tokenConfig(TOKEN);
        assertEq(pausedAfter, pausedBefore);
        assertEq(uint256(modeAfter), uint256(modeBefore));
        assertEq(collateralAfter, collateralBefore);
        assertEq(uint256(guardA.addressStatus(ACCOUNT)), uint256(statusBefore));
        assertTrue(factory.isTransferGuard(address(guardA)));
        assertTrue(factory.isTransferGuard(address(guardB)));
    }

    function _bytesToString(bytes memory data) private pure returns (string memory) {
        if (data.length == 0) return "empty revert data";
        return "revert data present";
    }
}
