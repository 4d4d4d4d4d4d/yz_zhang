// APPB-052b 全仓 lint（81 号 spec）。
//
// 探针：全仓**没有任何 lint**——没有配置、没有依赖、没有脚本。而
// `web/src/pages/Square.tsx` 里躺着一行：
//
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//
// **一条为不存在的检查写下的豁免注释。** 它和这一路反复出现的那个形状
// 是同一件事的反面：那些是「承诺了没人核对」，这一条是「豁免了没人检查」。
//
// 规则选择的原则与闸门一致：**只开会红在真问题上的那些**。
// 一个满口风格警告的 lint 会被人用 `--quiet` 或者干脆不跑——
// 那比没有 lint 更糟，因为它会让人以为有人在看。
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

export default tseslint.config(
  {
    // 生成物与依赖不看
    ignores: ['**/dist/**', '**/node_modules/**', '**/.expo/**', 'server/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.ts', '**/*.tsx'],
    plugins: { 'react-hooks': reactHooks },
    languageOptions: {
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: {
        window: 'readonly', document: 'readonly', localStorage: 'readonly',
        navigator: 'readonly', fetch: 'readonly', console: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly', alert: 'readonly',
        prompt: 'readonly', confirm: 'readonly', URL: 'readonly',
        IntersectionObserver: 'readonly', MediaQueryListEvent: 'readonly',
        HTMLElement: 'readonly', HTMLInputElement: 'readonly', File: 'readonly',
        FileList: 'readonly', Blob: 'readonly', FormData: 'readonly',
        createImageBitmap: 'readonly', globalThis: 'readonly', process: 'readonly',
        requestAnimationFrame: 'readonly', cancelAnimationFrame: 'readonly',
        crypto: 'readonly', TextEncoder: 'readonly', AbortController: 'readonly',
        React: 'readonly', __DEV__: 'readonly',
      },
    },
    rules: {
      // ---- 会红在真问题上的 ----
      // hook 依赖漏了 = 拿到旧闭包里的值，这类 bug 在界面上表现为
      // 「点了没反应」或者「显示的是上一次的数据」，最难查
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // 未用变量常常是「改了一半」的残留：删掉的调用留下的参数、
      // 重构后没人用的 import。参数与 rest 兄弟放宽（它们常是签名的一部分）
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_', varsIgnorePattern: '^_',
        ignoreRestSiblings: true,
      }],
      // `==` 在 JS 里会做隐式转换，'' == 0 为真——金额与状态判断上出过事
      eqeqeq: ['error', 'smart'],
      // 空的 catch 会把错误吞掉。这个仓里有意吞掉的地方都写了注释，
      // 所以允许带注释的空块
      'no-empty': ['error', { allowEmptyCatch: true }],

      // ---- 刻意关掉的：它们会在这个仓里刷出大量无意义警告 ----
      // 服务端响应在边界处是 unknown/any，逐个建类型是 SYNC-050 那条线的事
      '@typescript-eslint/no-explicit-any': 'off',
      // 断言在测试与 mock 里到处都是，报它等于报测试
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
  {
    // 构建/运行时配置文件是 CommonJS 跑在 Node 里：`require` / `module` /
    // `__dirname` 在那里是对的，不是错。**给它们单独一块，而不是把规则关掉**——
    // 关掉规则会连产品代码一起放过。
    files: ['**/*.config.js', '**/jest.setup.js', '**/*.cjs'],
    languageOptions: {
      globals: {
        require: 'readonly', module: 'writable', __dirname: 'readonly',
        process: 'readonly', jest: 'readonly', console: 'readonly',
      },
    },
    // 这一块是 Node/CommonJS：require 在这里是正确写法，不是错
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
  {
    // 测试文件：mock 与断言的写法与产品代码不同
    files: ['**/*.test.ts', '**/*.test.tsx'],
    rules: {
      '@typescript-eslint/no-unused-vars': 'off',
      'react-hooks/exhaustive-deps': 'off',
    },
  },
);
