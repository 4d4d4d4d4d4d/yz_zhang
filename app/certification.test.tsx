// APP-072 App 侧提交职业资质（87 号 spec）。
//
// 受限类目的单被服务端挡下来时，它给的指示是「请提交证件影像并通过平台核验后接单」。
// 在这一批之前，**App 上没有任何入口能满足它**——而 App 的主要用户正是
// 需要那张证的线下执行方。这几条测试钉住的是「入口在、而且按下去做对事」：
// 真的上传了、真的把拿到的 ref 带进提交、真的把服务端的驳回原文显示出来。
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PlatformClient } from '@platform/core';
import * as ImagePicker from 'expo-image-picker';
import { CertificationsScreen } from './certifications';

type Call = { method: string; path: string; body: unknown };

/** 按整条路径精确匹配（V84 的教训：`includes` 会让 `/wallet` 吃掉 `/wallet/ledger`）。 */
function makeClient(
  routes: Record<string, { status?: number; body: unknown }>,
  calls: Call[] = [],
): PlatformClient {
  const fetchImpl = (async (url: string, init?: { method?: string; body?: string }) => {
    const path = String(url).replace(/^.*\/api\/v1/, '').split('?')[0];
    calls.push({ method: init?.method ?? 'GET', path, body: init?.body ? JSON.parse(init.body) : null });
    const hit = routes[path];
    const status = hit?.status ?? 200;
    return {
      ok: status < 400, status,
      text: async () => JSON.stringify(hit ? hit.body : {}),
    };
  }) as unknown as typeof fetch;
  return new PlatformClient({ baseUrl: '', getToken: () => 'tok', fetchImpl });
}

const EMPTY = { '/users/me/certifications': { body: { active: [], applications: [] } } };

describe('APP-072 职业资质：服务端让他交，App 上要交得了', () => {
  it('选图 → 上传 → 把拿到的 ref 带进提交', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      ...EMPTY,
      '/files': { body: { url: 'https://x/y', ref: 'cert-abc.jpg' } },
    }, calls);
    render(<CertificationsScreen client={client} />);

    fireEvent.changeText(screen.getByPlaceholderText('资质名称（如：电工 / 家电维修）'), '电工');
    fireEvent.changeText(screen.getByPlaceholderText('证件上的姓名（须与实名一致）'), '张三');
    fireEvent.changeText(screen.getByPlaceholderText('证件编号'), 'EL-12345');
    fireEvent.press(screen.getByText('从相册选择'));
    await waitFor(() => expect(screen.getByText('已附 1 张证件影像')).toBeTruthy());

    fireEvent.press(screen.getByText('提交核验'));
    await waitFor(() => expect(screen.getByText('已提交，等待平台核验')).toBeTruthy());

    const post = calls.find((c) => c.method === 'POST' && c.path === '/users/me/certifications');
    expect(post).toBeTruthy();
    // 服务端认的是 snake_case，而且 images 必须是**上传后的 ref**，
    // 不是本地 file:// 路径——传本地路径服务端会收下一个它永远取不到的名字
    expect(post!.body).toMatchObject({
      name: '电工', holder_name: '张三', cert_number: 'EL-12345', images: ['cert-abc.jpg'],
    });
  });

  it('CERT-005 有效期填了就要传到服务端（否则 App 提交的证永不过期）', async () => {
    const calls: Call[] = [];
    const client = makeClient({
      ...EMPTY,
      '/files': { body: { url: 'https://x/y', ref: 'cert-abc.jpg' } },
    }, calls);
    render(<CertificationsScreen client={client} />);
    fireEvent.changeText(screen.getByPlaceholderText('资质名称（如：电工 / 家电维修）'), '电工');
    fireEvent.changeText(screen.getByPlaceholderText('证件上的姓名（须与实名一致）'), '张三');
    fireEvent.changeText(screen.getByPlaceholderText('证件编号'), 'EL-1');
    fireEvent.changeText(
      screen.getByPlaceholderText('有效期至 YYYY-MM-DD（证件上没有有效期才留空）'), '2030-01-01');
    fireEvent.press(screen.getByText('从相册选择'));
    await waitFor(() => expect(screen.getByText('已附 1 张证件影像')).toBeTruthy());
    fireEvent.press(screen.getByText('提交核验'));
    await waitFor(() => expect(screen.getByText('已提交，等待平台核验')).toBeTruthy());

    const post = calls.find((c) => c.method === 'POST' && c.path === '/users/me/certifications');
    // `decide()` 不会补有效期——这一栏丢了，就等于让 App 提交的证永不过期，
    // 而网页提交的会过期。那是悄悄给 App 用户开的一个后门。
    expect(post!.body).toMatchObject({ expires_at: '2030-01-01' });
  });

  it('没附影像就提交，显示服务端的原话而不是自己编一句', async () => {
    const client = makeClient({
      '/users/me/certifications': {
        // GET 空、POST 400：这个替身按路径匹配，所以用状态码表达 POST 的结果
        status: 400,
        body: { detail: { code: 'images_required', message: '需上传证件影像后再提交' } },
      },
    });
    render(<CertificationsScreen client={client} />);
    fireEvent.press(screen.getByText('提交核验'));
    await waitFor(() => expect(screen.getByText('需上传证件影像后再提交')).toBeTruthy());
  });

  it('证件姓名与实名不一致：把服务端的解释完整显示出来', async () => {
    const client = makeClient({
      '/users/me/certifications': {
        status: 400,
        body: {
          detail: {
            code: 'holder_mismatch',
            message: '证件持有人姓名与实名信息不一致，无法受理。职业资质必须由本人持有。',
          },
        },
      },
    });
    render(<CertificationsScreen client={client} />);
    fireEvent.press(screen.getByText('提交核验'));
    // 这句话解释了「为什么」，客户端重写一遍只会和服务端慢慢对不上（UI-075）
    await waitFor(() => expect(
      screen.getByText(/证件持有人姓名与实名信息不一致/),
    ).toBeTruthy());
  });

  it('已核准的资质与被驳回的原因都要看得见', async () => {
    const client = makeClient({
      '/users/me/certifications': {
        body: {
          active: ['电工'],
          applications: [
            { id: 1, name: '电工', status: 'approved', decision_reason: '', expires_at: '2030-01-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z' },
            { id: 2, name: '家电维修', status: 'rejected', decision_reason: '影像模糊，看不清证件编号', expires_at: null, created_at: '2026-02-01T00:00:00Z' },
          ],
        },
      },
    });
    render(<CertificationsScreen client={client} />);
    await waitFor(() => expect(screen.getByText('已核准：电工')).toBeTruthy());
    expect(screen.getByText('电工 · 已核准')).toBeTruthy();
    expect(screen.getByText('家电维修 · 未通过')).toBeTruthy();
    // 被驳回而看不到原因，用户只能反复提交同一份材料，每次再等一轮人工核验
    expect(screen.getByText('平台意见：影像模糊，看不清证件编号')).toBeTruthy();
  });

  it('没给权限时说清楚要去哪儿开，而不是什么都不发生', async () => {
    const spy = jest.spyOn(ImagePicker, 'requestMediaLibraryPermissionsAsync')
      .mockResolvedValue({ status: 'denied' } as never);
    try {
      render(<CertificationsScreen client={makeClient(EMPTY)} />);
      fireEvent.press(screen.getByText('从相册选择'));
      // 「按了没反应」是最糟的失败：用户会反复点同一个按钮
      await waitFor(() => expect(screen.getByText(/没有相册权限/)).toBeTruthy());
    } finally {
      spy.mockRestore();
    }
  });

  it('超过 2MB 的图在本地就拦住，不花用户的流量传上去再被拒', async () => {
    const big = 'A'.repeat(4 * 1024 * 1024); // 约 3MB 解码后
    const spy = jest.spyOn(ImagePicker, 'launchImageLibraryAsync')
      .mockResolvedValue({ canceled: false, assets: [{ base64: big, mimeType: 'image/jpeg' }] } as never);
    const calls: Call[] = [];
    try {
      render(<CertificationsScreen client={makeClient(EMPTY, calls)} />);
      fireEvent.press(screen.getByText('从相册选择'));
      await waitFor(() => expect(screen.getByText(/超过 2MB/)).toBeTruthy());
      expect(calls.some((c) => c.path === '/files')).toBe(false);
    } finally {
      spy.mockRestore();
    }
  });
});
