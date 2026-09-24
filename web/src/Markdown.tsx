// CNT-003 Markdown 渲染。
//
// **绝不用 dangerouslySetInnerHTML。** 把用户写的 Markdown 转成 HTML 再塞进
// DOM，是一个现成的存储型 XSS：博客正文是别人写的、所有人都会看，
// 一段 <img onerror=...> 就能在每个读者的浏览器里执行。
//
// 常见的做法是「转 HTML 再用 sanitizer 过一遍」——那要引入两个依赖，
// 而且安全性取决于 sanitizer 的黑名单跟不跟得上。这里换个方向：
// **直接解析成 React 元素**，从头到尾没有一个字符串被当作 HTML 解释。
// 代价是只支持一个够用的子集（标题/加粗/行内代码/代码块/列表/引用/链接/图片），
// 收益是这条路径上不存在 XSS 这个类别。
//
// 链接与图片的 href/src 仍要过协议白名单：`javascript:` 开头的 href
// 不需要 innerHTML 也能执行。
import type { ReactNode } from 'react';

const SAFE_URL = /^(https?:\/\/|\/)/i;

function safeUrl(raw: string): string | null {
  const url = raw.trim();
  // javascript: / data: / vbscript: 一律拒绝——只放行 http(s) 与站内相对路径
  return SAFE_URL.test(url) ? url : null;
}

/** 行内：`code`、**粗体**、[文本](链接)。按优先级依次切分，不做嵌套。 */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyPrefix}-i${i++}`;
    if (tok.startsWith('`')) {
      out.push(<code key={key}>{tok.slice(1, -1)}</code>);
    } else if (tok.startsWith('**')) {
      out.push(<strong key={key}>{tok.slice(2, -2)}</strong>);
    } else {
      const cut = tok.indexOf('](');
      const label = tok.slice(1, cut);
      const href = safeUrl(tok.slice(cut + 2, -1));
      // 拒掉的链接**保留文字**，不静默吞掉——否则作者不知道自己写错了
      out.push(href
        ? <a key={key} href={href} target="_blank" rel="noopener noreferrer">{label}</a>
        : <span key={key}>{label}</span>);
    }
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || '').split('\n');
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  let code: string[] | null = null;
  const pushCode = (lines: string[], key: string) =>
    blocks.push(<pre key={key}><code>{lines.join('\n')}</code></pre>);

  const flushList = () => {
    if (!list.length) return;
    const items = list;
    list = [];
    blocks.push(
      <ul key={`ul-${blocks.length}`}>
        {items.map((it, i) => <li key={i}>{inline(it, `l${blocks.length}-${i}`)}</li>)}
      </ul>,
    );
  };

  lines.forEach((raw, idx) => {
    if (raw.trim().startsWith('```')) {
      if (code === null) { flushList(); code = []; } else {
        pushCode(code, `pre-${idx}`);
        code = null;
      }
      return;
    }
    if (code !== null) { code.push(raw); return; }

    const line = raw.trimEnd();
    if (!line.trim()) { flushList(); return; }

    const img = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(line.trim());
    if (img) {
      flushList();
      const src = safeUrl(img[2]);
      if (src) blocks.push(<img key={`img-${idx}`} src={src} alt={img[1]} />);
      return;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      flushList();
      const level = heading[1].length;
      const content = inline(heading[2], `h${idx}`);
      blocks.push(level === 1 ? <h2 key={idx}>{content}</h2>
        : level === 2 ? <h3 key={idx}>{content}</h3>
          : <h4 key={idx}>{content}</h4>);
      return;
    }
    if (/^>\s?/.test(line)) {
      flushList();
      blocks.push(<blockquote key={idx}>{inline(line.replace(/^>\s?/, ''), `q${idx}`)}</blockquote>);
      return;
    }
    if (/^[-*]\s+/.test(line)) { list.push(line.replace(/^[-*]\s+/, '')); return; }
    flushList();
    blocks.push(<p key={idx}>{inline(line, `p${idx}`)}</p>);
  });
  flushList();
  if (code !== null) pushCode(code, 'pre-tail');

  return <div className="markdown">{blocks}</div>;
}
