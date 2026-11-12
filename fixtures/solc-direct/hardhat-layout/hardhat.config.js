// This file must never be loaded by CYDRA's compiler AST path.
require("fs").writeFileSync(process.env.CYDRA_HARDHAT_MARKER, "executed");
module.exports = { solidity: "0.8.26" };
