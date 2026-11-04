// APP-120（394 号 spec）App 里的图片 / 视频地址一律走共享 SDK 的 mediaUri，组件要的 baseUrl 一律传到。
//
// V417、V421 两次在任务详情页发现同一类缺陷：组件的 baseUrl 默认是空串，渲染它的地方忘了传，
// 预览图就成了 /api/v1/files/… 这样的相对路径——React Native 加载不了，真机上一张都出不来，
// 而组件自己的单测传了 baseUrl，所以一直是绿的。这里静态扫一遍，把这一类钉住。
import * as fs from 'fs';
import * as path from 'path';

const DIR = __dirname;
const SOURCES = fs.readdirSync(DIR)
  .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) && !f.endsWith('.d.ts'))
  .map((f) => ({ file: f, src: fs.readFileSync(path.join(DIR, f), 'utf8') }));

describe('APP-120 图片地址的两道闸门', () => {
  it('不手写拼地址：一律 mediaUri(baseUrl, path)', () => {
    const bad: string[] = [];
    const patterns = [/\$\{baseUrl\}\$\{/, /baseUrl \+ /, /startsWith\(['"]http['"]\)\s*\?/];
    for (const { file, src } of SOURCES) {
      src.split('\n').forEach((line, i) => {
        if (patterns.some((p) => p.test(line))) bad.push(`${file}:${i + 1}  ${line.trim()}`);
      });
    }
    expect(bad).toEqual([]);
  });

  it('baseUrl 默认空串的组件，每一处用到都要传 baseUrl', () => {
    // 找出 props 里写着 baseUrl = '' 的导出组件
    const names = new Set<string>();
    for (const { src } of SOURCES) {
      for (const m of src.matchAll(/export function (\w+)\(\{[^)]*?baseUrl = ''/g)) names.add(m[1]);
    }
    expect(names.size).toBeGreaterThanOrEqual(3);   // 扫描器本身得看得见它们
    const missing: string[] = [];
    for (const { file, src } of SOURCES) {
      for (const name of names) {
        const re = new RegExp(`<${name}\\b([\\s\\S]*?)\\/?>`, 'g');
        for (const m of src.matchAll(re)) {
          if (!/\bbaseUrl=/.test(m[1])) missing.push(`${file}: <${name} …> 没传 baseUrl`);
        }
      }
    }
    expect(missing).toEqual([]);
  });
});
