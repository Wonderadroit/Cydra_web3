# Held-out authorization replay after source-closure parser fixes

Date: 2026-10-11

## Run evidence

- Paired campaign workflow: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38151022817
- Artifact: `cydra-heldout-multi-target-closure-v2` (artifact ID `11706736202`)
- Positive authorization control (historical known issue): https://github.com/Wonderadroit/Cydra_web3/actions/runs/38149408447
- Protected negative control: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38149411553

## 0x Settler

- Repository: https://github.com/0xProject/0x-settler
- Pinned revision: `872b0e4cc83cce6a75eb4a1705f5bfd06e21a6c5`
- Entry source: `src/chains/Mainnet/Intent.sol`
- Compiler status: `success`
- Dependency closure: 64 sources, zero unresolved imports
- Extracted evidence: 22 semantic relationships, 61 parameter constraints
- Authorization hypotheses: zero
- Finding gate: `NOT_READY`

The commented-out `CurveTricrypto` import no longer falsely blocks the dependency closure. This is a parser correctness improvement, not a security finding. The selected target's modeled surface does not currently yield a supported privileged-state authorization hypothesis. Its inherited meta-transaction and signature/witness boundary is not yet covered by an adequate executable experiment contract, so this run must not be interpreted as a negative security verdict.

## CoW Protocol allow-list authentication

- Repository: https://github.com/cowprotocol/contracts
- Pinned revision: `6ebbd810ff2da635fb6f88e9a15fde196f8c852a`
- Entry source: `src/contracts/GPv2AllowListAuthentication.sol`
- Compiler status: `success`
- Dependency closure: 5 sources, zero unresolved imports
- Extracted evidence: 15 semantic relationships, zero parameter constraints
- Authorization hypotheses: zero
- Finding gate: `NOT_READY`

The source inventory identifies `initializeManager` as an externally callable initializer that writes `manager`. Its disposition remains `DEPLOYMENT_STATE_REQUIRED`: a source-only/local deployment does not prove the production proxy was left uninitialized. The ordinary manager and solver setters carry explicit access-control modifiers. No unauthorized production state transition has been demonstrated.

## Control outcomes

- The historical Decent Bridge `setRouter` positive control reproduced the unauthorized state mutation; the patched variant passed, with causal and independent reproduction checks marked verified. This is a known historical control, not a novel bounty finding.
- The protected `setWhitelist` negative control passed and was classified `not_confirmed`.

## Decision

The parser and regression milestones are complete. The bounty-finding milestone is **not complete**: neither held-out target produced a supported hypothesis and runnable target-specific exploit experiment. Do not submit a report based on these artifacts.

## Next capability closure

1. Add an experiment contract for inherited meta-transaction authorization: signer/witness binding, action-array integrity, first-action authentication, and rejection of an unauthorized solver. Execute it against the pinned Settler source and a protected negative fixture.
2. For CoW, collect independent deployment evidence for proxy address `0xbbfB9a525ACdd2aB3A5Eb5fc9Ab8CF53b881000e`, implementation `0xFeDbc87123caF3925145e1bD1Be844c03b36722f`, and the initialization call/state. Do not infer a production takeover from `initializeManager` alone.
3. Only promote a candidate if a target-specific unauthorized action succeeds on the pinned vulnerable target, fails under the relevant guard/fix, and reproduces independently.
