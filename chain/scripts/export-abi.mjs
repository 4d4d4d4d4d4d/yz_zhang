import fs from 'node:fs';
import { compile } from './compile.mjs';
for (const [name, file] of [['TaskEscrow','escrow-abi.json'], ['BusinessRecords','records-abi.json']]) {
const target = new URL(`../../web/src/chain/${file}`, import.meta.url);
const contents = JSON.stringify(compile(name).abi, null, 2) + '\n';
if (process.argv.includes('--check')) {
  if (fs.readFileSync(target, 'utf8') !== contents) throw new Error('Web ABI is stale: npm run abi');
  console.log('Web ABI matches compiled contract');
} else fs.writeFileSync(target, contents);

}
