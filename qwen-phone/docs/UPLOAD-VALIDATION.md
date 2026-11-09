# 上传前检查（2026-11-09）

- 发布内容：小千源码、脚本、测试、文本工程报告与当前交接说明。
- 排除内容：模型、SDK、第三方运行库、构建产物、签名、资料库、原始截图/UI树/设备日志。
- 扫描上传文件：未发现已知调试口令、个人设备序列号、个人主目录、私钥块或常见访问令牌格式；这不替代独立安全审查。
- 重新运行8组宿主机测试：task-scope、query-target、query-policy、ui-audit、capture-delivery、native-bridge、conversation-display、voice，全部通过。
- 发布副本Python语法、shell构建脚本语法、phone.py帮助入口检查通过。部署脚本改为显式要求QWEN_PHONE_SERIAL。
- 本次操作是源码交接，没有重新开展真机业务验收或宣称商业上线。构建和真机边界见HANDOFF.md。
