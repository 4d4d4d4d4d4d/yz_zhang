# OPC external evidence checkpoints

`EvidenceRegistry.sol` publishes SHA-256 audit-chain checkpoints on an EVM network. It does not hold funds, issue equity, determine legal validity, or turn a platform witness into a CA signature. Tested on an ephemeral local EVM; no public-chain deployment is claimed.

## Reproducible local verification

From `chain/`: `npm ci`, `npm run compile`, `npm test`. Compiler and dependencies are pinned in the lockfile. The test starts a loopback Hardhat node, deploys the real bytecode and exercises unauthorized writes, continuity, immutable history, pause and two-step ownership transfer. Never use Hardhat's public development keys on a live network.

## Deployment and publication

Configure `CHAIN_RPC_URL`, `CHAIN_ID`, `CHAIN_OWNER` (prefer a multisig), `CHAIN_PUBLISHER`, `CHAIN_KEY_FILE` (0600, outside the repository), and `CHAIN_CONFIRMATIONS` (network-specific; default 12). `CHAIN_SEND=1 node scripts/publish.mjs --deploy` deploys. This costs network gas and requires an operator-funded account. This has NOT been run against a public network.

For checkpoints set `CHAIN_CONTRACT`, `PLATFORM_API_BASE` (e.g. `http://127.0.0.1:18080/api/v1` through SSH), and a unique `CHAIN_RECEIPT_FILE`. `node scripts/publish.mjs` only prints a plan. `CHAIN_SEND=1 node scripts/publish.mjs` broadcasts and waits for confirmations. Persist receipt files and monitor transaction failures; a timeout requires receipt reconciliation, never blind resend. Use one publisher process per contract. The contract enforces consecutive ranges across competing transactions. Ownership changes require acceptance by the new owner; historical entries have no update/delete operation.

The server's read-only `/api/v1/anchors/blockchain` uses `PLATFORM_CHAIN_RPC_URL`, `PLATFORM_CHAIN_ID`, `PLATFORM_CHAIN_CONTRACT`, `PLATFORM_CHAIN_CONFIRMATIONS`. It compares the checkpoint to the local chain at a confirmed canonical block using EIP-1898. RPCs must support block-hash-based `eth_call`. No publisher key belongs in the API container. Missing configuration returns `unconfigured`, wrong digest returns `mismatch`, and RPC failure returns `unavailable`; none reports verified success.

Before production: independent contract/security review, approved network and jurisdiction, verified deployment source/address, monitored RPC, key recovery/rotation drill, gas budget, and chain-specific finality policy. Twelve blocks is a configurable depth, not universal finality.

## TaskEscrow — executable task settlement

See [the implementation and operations guide](../docs/SMART-CONTRACTS.md). `TaskEscrow.sol` is separate from `EvidenceRegistry`: it escrows an explicitly chosen ERC20 token and enforces acceptance, sequential milestones, review and arbitration deadlines, refunds, mutual cancellation, scoped machine delegation, platform fees and withdrawals. It is not a renminbi payment gateway, legal-signature provider or equity register.

`npm test` runs both contracts against real isolated local EVMs (ports 18545/18546). `npm run abi:check` checks the Web ABI. `npm run demo` starts a loopback-only demonstration at port 18547 and creates a funded two-milestone task; it resets when restarted. No public-chain deployment or external security audit has taken place.

`BusinessRecords.sol` adds independent organizational namespaces, four document categories (equity/agreement/legal/financial), append-only linked versions, corrections, version-specific signer/quorum snapshots, revocable attestations with retained event history, scoped expiring publication delegates and two-step controller handover. Web `/records` includes local AES-GCM encryption and salted document commitments. Organizational identity and legal authority are not inferred from a wallet. See the guide above for deployment, privacy and legal boundaries.

## Durable operations

Node 24 is required for the SQLite event index and settlement journal. Compile artifacts before running the operational scripts. `scripts/index-events.mjs` supports confirmed event indexing, restart, reorg rollback, canonical paginated export, backups and metrics. `scripts/plan-settlements.mjs` only produces unsigned timeout actions; `scripts/run-settlements.mjs` defaults to dry-run and requires explicit fee caps and a dedicated signing account to broadcast. See [operator commands and remaining production work](../docs/COMMERCIAL-READINESS.md). No production chain service or paid broadcaster is enabled by this delivery.
