// LAW-051 / KB-023 「不懂就问」在 App 上的行为（97 号 spec）。
//
// 手机上这一页尤其要紧：问「这事我不懂，该怎么办」的那一刻，
// 人很少坐在电脑前。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import { AskScreen, ExperienceBlock } from './ask';

const DISCLAIMER = '以上内容仅为一般性法律信息，不构成法律意见；正式法律服务请咨询执业律师。';

function makeClient(routes: Record<string, unknown>): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    const hit = Object.keys(routes).find((k) => k === path);
    return { ok: true, status: 200, text: async () => JSON.stringify(hit ? routes[hit] : []) };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const asked = (extra: Record<string, unknown>) =>
  ({ '/legal/ask': { disclaimer: DISCLAIMER, ...extra } });

describe('LAW-051 三种结局是三件不同的事', () => {
  it('人身风险：不给平台内的补救入口', async () => {
    const client = makeClient(asked({
      answer: '该问题涉及人身安全或刑事风险，请立即拨打 110 报警或联系专业机构，平台 AI 不提供此类解答。',
      refused: true, refused_reason: 'high_risk',
      // 故意给一个 remedy：**客户端不该因为服务端给了就摆这个按钮**。
      // 判据是 refused_reason，不是 remedy 在不在——否则这条断言会因为
      // 「服务端刚好没给」而通过，那是 V118 教过的那种假绿。
      remedy: { action: 'publish_task', category: '法律咨询', label: '发布法律咨询任务（由执业律师接单）' },
    }));
    const onPublish = jest.fn();
    render(<AskScreen client={client} onPublish={onPublish} />);
    fireEvent.changeText(screen.getByPlaceholderText('描述你的问题…'), '对方威胁我');
    fireEvent.press(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText('这个问题平台不作解答')).toBeTruthy());
    expect(screen.getByText(/平台的任何流程都不优先于此/)).toBeTruthy();
    // 紧急升级旁边不该有一个「发任务」按钮
    expect(screen.queryByText(/发布法律咨询任务/)).toBeNull();
    expect(onPublish).not.toHaveBeenCalled();
  });

  it('超出知识库：补救真的把人送去发任务，且带着服务端给的类目', async () => {
    const client = makeClient(asked({
      answer: '该问题超出平台法律知识库范围，建议通过「找律师」发布法律咨询任务，由执业律师解答。',
      refused: true, refused_reason: 'out_of_scope',
      remedy: { action: 'publish_task', category: '法律咨询', label: '发布法律咨询任务（由执业律师接单）' },
    }));
    const onPublish = jest.fn();
    render(<AskScreen client={client} onPublish={onPublish} />);
    fireEvent.changeText(screen.getByPlaceholderText('描述你的问题…'), '外星人宅基地');
    fireEvent.press(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText('平台知识库答不了这一条')).toBeTruthy());
    fireEvent.press(screen.getByText('发布法律咨询任务（由执业律师接单）'));
    // 类目不在客户端写死：服务端改类目名时，写死的那个会静默把人送错地方
    expect(onPublish).toHaveBeenCalledWith('法律咨询');
  });

  it('命中知识库：既不报警也不劝他发任务，但免责声明照样在', async () => {
    const client = makeClient(asked({
      answer: '平台电子合约经双方在线确认签署后成立。',
      refused: false, refused_reason: '', remedy: null,
    }));
    render(<AskScreen client={client} />);
    fireEvent.changeText(screen.getByPlaceholderText('描述你的问题…'), '合约有效力吗');
    fireEvent.press(screen.getByText('提问'));

    await waitFor(() => expect(screen.getByText(/经双方在线确认签署后成立/)).toBeTruthy());
    expect(screen.queryByText('这个问题平台不作解答')).toBeNull();
    expect(screen.queryByText('平台知识库答不了这一条')).toBeNull();
    expect(screen.getByText(DISCLAIMER)).toBeTruthy();
  });
});

describe('KB-023 平台攒的经验要读得回来', () => {
  it('退化的检索必须说出来', async () => {
    const client = makeClient({
      '/knowledge/search': {
        results: [{ id: 1, score: 1, text: '跑腿 杭州 跑腿·杭州' }],
        semantic: false, degraded: true, model: 'local-bow-256',
      },
    });
    render(<ExperienceBlock client={client} />);
    fireEvent.changeText(screen.getByPlaceholderText('搜经验：保洁 / 跑腿 / 软件开发…'), '跑腿');
    fireEvent.press(screen.getByText('检索'));

    await waitFor(() => expect(screen.getByText(/不是语义检索/)).toBeTruthy());
    expect(screen.getByText(/退化为词面命中/)).toBeTruthy();
  });

  it('真语义检索时不画那句提示', async () => {
    const client = makeClient({
      '/knowledge/search': { results: [], semantic: true, degraded: false, model: 'real-embed-1' },
    });
    render(<ExperienceBlock client={client} />);
    fireEvent.changeText(screen.getByPlaceholderText('搜经验：保洁 / 跑腿 / 软件开发…'), '跑腿');
    fireEvent.press(screen.getByText('检索'));

    await waitFor(() => expect(screen.getByText(/没有命中/)).toBeTruthy());
    expect(screen.queryByText(/不是语义检索/)).toBeNull();
  });

  it('经验卡显示结果好坏——失败案例同样入库', async () => {
    const client = makeClient({
      '/knowledge/cards': [
        { id: 2, category: '保洁', city: '上海', title: '保洁·上海', price_actual_cents: 90000,
          duration_days: 0, outcome: 'disputed', has_decomposition: true },
      ],
    });
    render(<ExperienceBlock client={client} />);
    fireEvent.press(screen.getByText('看最近的'));
    // KB-004：不显示这一列的话，有纠纷的这笔会被当成行情
    await waitFor(() => expect(screen.getByText(/有纠纷/)).toBeTruthy());
    expect(screen.getByText(/保洁 · 上海 · 含分解/)).toBeTruthy();
  });

  it('空结果说清为什么是空的', async () => {
    const client = makeClient({ '/knowledge/cards': [] });
    render(<ExperienceBlock client={client} />);
    fireEvent.press(screen.getByText('看最近的'));
    await waitFor(() => expect(screen.getByText(/没有闭环就没有经验/)).toBeTruthy());
  });
});
