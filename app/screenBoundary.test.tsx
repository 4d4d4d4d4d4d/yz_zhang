// APP-092 App 屏幕错误边界（183 号 spec）：一屏渲染出错只坏这一屏，说明为什么、怎么办，点返回回到上一层；主框架确实套着它。
import { readFileSync } from 'fs';
import { join } from 'path';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { ScreenBoundary } from './ScreenBoundary';

function Boom(): JSX.Element { throw new TypeError('rows.map is not a function'); }

describe('APP-092 App 屏幕错误边界', () => {
  beforeEach(() => jest.spyOn(console, 'error').mockImplementation(() => {}));
  afterEach(() => jest.restoreAllMocks());

  it('一屏出错：换成说明，点返回回到上一层；只记错误类型', () => {
    const back = jest.fn();
    render(<ScreenBoundary onBack={back}><Boom /></ScreenBoundary>);
    expect(screen.getByLabelText('这一页没加载出来')).toBeTruthy();
    expect(screen.getByText(/一直这样，请在「我的空间 → 客服」提单/)).toBeTruthy();
    fireEvent.press(screen.getByText('← 返回'));
    expect(back).toHaveBeenCalled();
    expect(console.error).toHaveBeenCalledWith('screen_render_failed', 'TypeError');
  });

  it('没出错：照常显示', () => {
    render(<ScreenBoundary onBack={() => {}}><Text>正常的一屏</Text></ScreenBoundary>);
    expect(screen.getByText('正常的一屏')).toBeTruthy();
    expect(screen.queryByLabelText('这一页没加载出来')).toBeNull();
  });

  it('主框架的主体区域套着它，并按当前屏复位（换一屏 key 就变）', () => {
    const src = readFileSync(join(__dirname, 'App.tsx'), 'utf8');
    expect(src).toMatch(/<ScreenBoundary key=\{activeTask \? `task-\$\{activeTask\.id\}` : overlay \? `overlay-\$\{overlay\.kind\}` : `tab-\$\{tab\}`\}/);
    const body = src.slice(src.indexOf('<View style={styles.body}>'), src.indexOf('</ScreenBoundary>'));
    expect(body).toContain('<TaskDetailScreen');
    expect(body).toContain("tab === 'messages'");
  });

  it('APP-094 出错时把错误类型交给上报回调；上报自己出错也不影响说明', () => {
    const report = jest.fn(() => { throw new Error('网络断了'); });
    render(<ScreenBoundary onBack={() => {}} onError={report}><Boom /></ScreenBoundary>);
    expect(report).toHaveBeenCalledWith('TypeError');
    expect(screen.getByLabelText('这一页没加载出来')).toBeTruthy();
  });

  it('APP-094 主框架上报的屏名不带任务 id', () => {
    const src = readFileSync(join(__dirname, 'App.tsx'), 'utf8');
    expect(src).toContain("const screenName = activeTask ? 'task' : overlay ? `overlay-${overlay.kind}` : `tab-${tab}`;");
    expect(src).toContain("client.reportRenderError('app', screenName, kind)");
  });
});
