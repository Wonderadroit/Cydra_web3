# Blind authorization campaign — OpenZeppelin ERC7786OpenBridge

## Intake

- Program: OpenZeppelin
- Official scope: https://immunefi.com/bug-bounty/openzeppelin/scope/
- Official resources: https://immunefi.com/bug-bounty/openzeppelin/resources/
- Target asset: ERC7786OpenBridge, listed at the exact pinned commit in the official scope
- Target repository: https://github.com/OpenZeppelin/openzeppelin-community-contracts
- Target revision: 0361935dc5edd233adbb9fbae5871ccbb8c739d8
- Source: contracts/crosschain/ERC7786OpenBridge.sol
- Run: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124629642
- Artifact: https://github.com/Wonderadroit/Cydra_web3/actions/runs/38124629642/artifacts/11696905609
- Mode: local-only source/compiler/Foundry testing; no live transactions.

## Outcome

The runner failed closed with NO_AUTH_HYPOTHESIS, so no candidate experiment was executed and no vulnerability was found or ruled out.

The model listed 18 functions. The visible administrative methods included:
- addGateway — onlyOwner
- removeGateway — onlyOwner
- setThreshold — onlyOwner, modeled write to _threshold
- registerRemoteBridge — onlyOwner, modeled write to _remotes
- pause and unpause — onlyOwner

The model did not surface direct writes for addGateway/removeGateway, which mutate an EnumerableSet-backed storage structure through library calls. This is a remaining state-effect modeling limitation, but the observed methods are owner-protected. No authorization bypass was demonstrated.

## Interpretation

This is a NOT_SELECTED / BLOCKED measurement, not a finding and not proof that the target is secure. The exact source commit is included in the official OpenZeppelin scope; the test was local-only. Do not add an OpenBridge-specific exception.

The next generic modeling question is how to represent state effects of library methods operating on storage references, then validate the result against both protected and deliberately vulnerable controls. The expected vulnerable function must remain hidden from the hypothesis engine.
