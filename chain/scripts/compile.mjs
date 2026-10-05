import fs from 'node:fs';
import path from 'node:path';
import solc from 'solc';
export function compile() {
  const input = { language: 'Solidity', sources: { 'EvidenceRegistry.sol': {
    content: fs.readFileSync(new URL('../contracts/EvidenceRegistry.sol', import.meta.url), 'utf8')
  } }, settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: 'paris',
    outputSelection: { '*': { '*': ['abi', 'evm.bytecode.object'] } } } };
  const output = JSON.parse(solc.compile(JSON.stringify(input), { import: name => {
    return { contents: fs.readFileSync(path.resolve('node_modules', name), 'utf8') };
  } }));
  const errors = (output.errors || []).filter(e => e.severity === 'error');
  if (errors.length) throw new Error(errors.map(e => e.formattedMessage).join('\n'));
  const result = output.contracts['EvidenceRegistry.sol'].EvidenceRegistry;
  return { abi: result.abi, bytecode: '0x' + result.evm.bytecode.object, compiler: solc.version() };
}
if (process.argv[1] === new URL(import.meta.url).pathname) {
  fs.mkdirSync('artifacts', { recursive: true });
  fs.writeFileSync('artifacts/EvidenceRegistry.json', JSON.stringify(compile(), null, 2));
  console.log('Compiled EvidenceRegistry');
}
