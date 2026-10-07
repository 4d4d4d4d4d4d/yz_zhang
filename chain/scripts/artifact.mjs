import fs from 'node:fs';
export function loadArtifact(name) {
  if (!['TaskEscrow', 'BusinessRecords'].includes(name)) throw new Error('Unknown contract type');
  const file = new URL(`../artifacts/${name}.json`, import.meta.url);
  if (!fs.existsSync(file)) throw new Error('Compile artifacts before running: npm run compile');
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}
