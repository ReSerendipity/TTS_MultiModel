# Changelog

> 说明：以下历史条目中提及的 `AGENTS.md` 为**本地维护、不随仓库分发**的资产（`.gitignore` 已忽略）；条目仅为变更发生时的历史记录，clone 读者无需在仓库中查找该文件。

## [2.3.0](https://github.com/ReSerendipity/TTS_MultiModel/compare/v2.2.3...v2.3.0) (2026-09-22)


### Features

* add GitHub Pages online demo (pure frontend simulation) ([dad34bc](https://github.com/ReSerendipity/TTS_MultiModel/commit/dad34bcb2109be7e5936f5e58a50e01bf69f849d))
* add social media links to help page ([40e6f4c](https://github.com/ReSerendipity/TTS_MultiModel/commit/40e6f4c40953ba4194ca0f513705e8f7d956aeda))
* **app:** /readyz 升级为模型就绪流量闸门 ([0cac4b4](https://github.com/ReSerendipity/TTS_MultiModel/commit/0cac4b413c21162ffdce267f114f5ddc63bdc0a8))
* **app:** 应用层集成 SRE/可观测性能力 + 修复相对导入深度错误 ([7183fe2](https://github.com/ReSerendipity/TTS_MultiModel/commit/7183fe25cfe767f8f8a24bf6c208e1ee8e5d0a61))
* **C2:** TTS voicebox MCP 桥接 + 引擎适配器; 第三方声明与 gitignore 更新 ([c02b908](https://github.com/ReSerendipity/TTS_MultiModel/commit/c02b908fc1815630351c735a36ab4612d1b3faf8))
* **ci:** 锁集交叉约束检查，抓 issue [#97](https://github.com/ReSerendipity/TTS_MultiModel/issues/97) 那类上界/通配冲突 ([e104809](https://github.com/ReSerendipity/TTS_MultiModel/commit/e1048093cba7008e1f4eb9a57f42f79257bc05ed))
* **ci:** 锁集交叉约束检查（抓 [#97](https://github.com/ReSerendipity/TTS_MultiModel/issues/97) 那类上界/通配冲突） ([4f82a21](https://github.com/ReSerendipity/TTS_MultiModel/commit/4f82a21df004e378de56cfd98c44038430f1dfd5))
* **compliance:** add script workshop legal warning (5 locales) - prohibit synthesizing protected voices per IndexTTS DISCLAIMER ([4ae3cbd](https://github.com/ReSerendipity/TTS_MultiModel/commit/4ae3cbd1429db235701f37516240a0f8aca0e91c))
* **data-governance:** generation_history 血缘字段扩展 + 双轨训练架构文档收敛 ([a495079](https://github.com/ReSerendipity/TTS_MultiModel/commit/a495079fd649c21985b5009b477b68b638c8b77f))
* **data-governance:** P0+P1 核心数据治理落地 ([e608451](https://github.com/ReSerendipity/TTS_MultiModel/commit/e60845158d5a43b94b1221f845d9fd9aad90cffe))
* **data-governance:** 新增治理/验证/诊断脚本集(18个) ([85eb3d1](https://github.com/ReSerendipity/TTS_MultiModel/commit/85eb3d13c1214ec3967f0aaa7063875a68fe15df))
* **desktop:** 移植 Tauri v2 桌面壳并适配 TTS 语义（报告 P1-2） ([a9b8947](https://github.com/ReSerendipity/TTS_MultiModel/commit/a9b8947d9e13df8ddebef908bf87fdc9beec8524))
* **dist:** 便携分卷打包/NSIS 安装器/增量更新装配链（对应《桌面分发与安全加固-20260910》P1-3） ([6294622](https://github.com/ReSerendipity/TTS_MultiModel/commit/6294622df0802e3353b064e3031b4cb7c8d1b57b))
* **dist:** 发布门禁五步 + 完整性诊断脚本（对应《桌面分发与安全加固-20260910》P2-1） ([7666397](https://github.com/ReSerendipity/TTS_MultiModel/commit/76663979349bb015b55f38c36d21f0604895e450))
* **dist:** 发布门禁真实模式（真实资产五步门禁，P2-1 扩展） ([a30d2f2](https://github.com/ReSerendipity/TTS_MultiModel/commit/a30d2f2b2a5009d75226af22e774dad8745014be))
* **dist:** 统一模型下载器 + 下载/许可文档 ([#56](https://github.com/ReSerendipity/TTS_MultiModel/issues/56)) ([7e1535e](https://github.com/ReSerendipity/TTS_MultiModel/commit/7e1535ebccefca3981bef478032d82dfafbf93ed))
* **dist:** 解包器检测 model 缺失时提示官方源下载路径（模型可选分发） ([68b5731](https://github.com/ReSerendipity/TTS_MultiModel/commit/68b5731cee874459502f8549a9434bb546d91200))
* **engine:** gptsovits robustness + en/zh i18n + template polish ([cafac6d](https://github.com/ReSerendipity/TTS_MultiModel/commit/cafac6dd17889fbb3fd073978dc35e9d10f5feaa))
* **engine:** harden dotstts load() + ja/ko i18n parity ([4bea877](https://github.com/ReSerendipity/TTS_MultiModel/commit/4bea8771d4b17154f8b904bf2f49545bbec3bdcc))
* **engines:** integrate GPT-SoVITS and dots.tts as declarative engines ([6221cc3](https://github.com/ReSerendipity/TTS_MultiModel/commit/6221cc3078db415fd01677f6d4ea04569e27627e))
* **engines:** 新增只读引擎发现/能力查询端点（/api/engines） ([#55](https://github.com/ReSerendipity/TTS_MultiModel/issues/55)) ([024572e](https://github.com/ReSerendipity/TTS_MultiModel/commit/024572e56f9c9dfad82237f89b71214e0212df38))
* full-feature demo v2 - 15 tabs/command palette/persona/history ([fef46c1](https://github.com/ReSerendipity/TTS_MultiModel/commit/fef46c13ff7826680dde2a5cfc3d767a18b5d1f7))
* **generate:** 信号量超时 429/硬超时 503 + Retry-After，接入 bad_case 质量检测，db.insert 异步化 (S2-1/S2-2/S3-3) ([2a239da](https://github.com/ReSerendipity/TTS_MultiModel/commit/2a239dab7c2c998417cdfe1c078a5d3e01816f21))
* **hooks:** 新增 .githooks —— DCO 自动签名与校验、依赖漂移提醒 ([fd1667a](https://github.com/ReSerendipity/TTS_MultiModel/commit/fd1667a960b2c340550d5ede5a1e02269aef269c))
* **indextts20:** 独立侧栏分组与页面，并修复 IndexTTS 无法出音与引擎切不回 ([8d45578](https://github.com/ReSerendipity/TTS_MultiModel/commit/8d45578ef11f39f33769285f23ed76bd8b35c54e))
* **indextts2:** 新增可对比的 IndexTTS 2.0 引擎并清理误导残留 ([0cb9af8](https://github.com/ReSerendipity/TTS_MultiModel/commit/0cb9af8ba91ecdcdcc27ff18c864082b48e93d9c))
* **infra:** vendor tn stubs + opencc fallback + install docs ([6ff5e3f](https://github.com/ReSerendipity/TTS_MultiModel/commit/6ff5e3f006db2d929922dd5ed6760fed34436f8c))
* **logging:** 完善日志机制 - 统一格式(PID/TID/模块位置/request_id) + 环境变量覆盖 + 双通道输出 ([9097178](https://github.com/ReSerendipity/TTS_MultiModel/commit/9097178276570fc9662eee3553dcb75ae0e4c54b))
* **model_registry:** add MultiEngineRegistry for concurrent engine management ([176ef52](https://github.com/ReSerendipity/TTS_MultiModel/commit/176ef52bc2106ee9461f3a6bfd763f6aa62b020b))
* **observability:** 可观测性与韧性基础设施落地 (SRE P0~P2) ([1652049](https://github.com/ReSerendipity/TTS_MultiModel/commit/165204997237632225418b64ff8a8178de7b1245))
* **observability:** 运维稳定性 P1/P1-4 落地——OOM耗尽异常、p95直方图SLO、受控重载计数持久化 ([83f21f2](https://github.com/ReSerendipity/TTS_MultiModel/commit/83f21f2cabdb225a790fd893932cf472a3372a0f))
* **openai:** /v1/audio/speech 支持 stream 参数 (S3-1) ([e21a6fb](https://github.com/ReSerendipity/TTS_MultiModel/commit/e21a6fbf7af8957b79283b2354ee45a7621bddaf))
* **ops:** 运维能力补齐 —— 备份/回滚/部署清单 (SRE P1/P3) ([e9298fa](https://github.com/ReSerendipity/TTS_MultiModel/commit/e9298fadd65847d753725d647728328f322027ea))
* P0 Voicebox VC 真实接入 — 基于 OpenVoice ToneColorConverter 实现零样本音色转换 ([0e302f4](https://github.com/ReSerendipity/TTS_MultiModel/commit/0e302f4c0cd6930f677f852cf224da9204426a09))
* P1 Step-Audio-EditX 音频编辑引擎接入 ([dcde9df](https://github.com/ReSerendipity/TTS_MultiModel/commit/dcde9df5f5ae4b6db52d96e1630721e1f872d38e))
* P2 学习报告成果落地 — dia剧本配音schema + LoRA训练编排器 + 模型格式评估 ([bf62a2f](https://github.com/ReSerendipity/TTS_MultiModel/commit/bf62a2f0982c3ba5a87e5dc4110ee9423aded805))
* **perf:** apply OPTIMIZATION spec (history FTS5 + keyset pagination + audio streaming) ([41c7757](https://github.com/ReSerendipity/TTS_MultiModel/commit/41c775731c91fb78a8ed47d0703052c0f92a511b))
* **perf:** 运维稳定性 P0-2/P0-3 落地——冷启动测量修复 + GPU MTTR 基线门禁链 ([b423bcf](https://github.com/ReSerendipity/TTS_MultiModel/commit/b423bcf690caf744f1995236fbc41e591196d0d9))
* **persona:** 实现 /api/persona/save 并修复语言码三套词表不通 ([8234f86](https://github.com/ReSerendipity/TTS_MultiModel/commit/8234f86502b2f8906c3d74919facdb5611e37c42))
* **pwa,stage-e:** PWA Phase 1 基础设施（manifest + Service Worker + 客户端控制器） ([307ddcf](https://github.com/ReSerendipity/TTS_MultiModel/commit/307ddcf525d580e95333bd4cb7e481202a11737d))
* **pwa,stage-e:** PWA Phase 2 — IndexedDB 音频缓存（SW 拦截 + LRU + 跨标签页同步） ([9731f3a](https://github.com/ReSerendipity/TTS_MultiModel/commit/9731f3ac7398905316daafcef0577a9026b11c95))
* **quality:** 能力声明=&gt;验证门禁 —— check_declared_capabilities ([79042d3](https://github.com/ReSerendipity/TTS_MultiModel/commit/79042d348439bb789171a5fe6c0c609c8fb0742b))
* **security:** API 认证覆盖 /v1 与 SSE + 结构化审计日志 (H1/M6/M7) ([86dfb69](https://github.com/ReSerendipity/TTS_MultiModel/commit/86dfb69a2e573fc85da0f65473a6d37509c23978))
* **security:** complete security hardening based on assessment report ([f623304](https://github.com/ReSerendipity/TTS_MultiModel/commit/f62330493b9732bdd17ac5387917533d00ea3969))
* **security:** HTTPS/SSL 接线 + 启动完整性阻断 + 模型权重校验 + PII 留存清理 + CORS 修正 ([a600854](https://github.com/ReSerendipity/TTS_MultiModel/commit/a6008544a32469dc86ccc393226a2deaa4045167))
* **security:** integrity manifest signing (Ed25519+HMAC) with enforce, 3-tier watermark failure strategy, portable pinning ([5e8d781](https://github.com/ReSerendipity/TTS_MultiModel/commit/5e8d781ffb886fd4a559ed9ac24e2c829b2b4991))
* **security:** P0 克隆频率限制 + 参考音频质量门槛 + 训练接口限流 ([07ccb21](https://github.com/ReSerendipity/TTS_MultiModel/commit/07ccb214438d96ce39291a0faaa5843b6f969174))
* **security:** P1 审计轮转 + PII加密默认开启 + uploads递归TTL清理 ([7dfd179](https://github.com/ReSerendipity/TTS_MultiModel/commit/7dfd1798b583cd9541b12f1060ec0364c7a83947))
* **security:** P1 水印HMAC密钥版 + AI标识三件套 + P3水印强度配置接线 ([0c59343](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c5934350a53841f9e5cdd155c1c1ea9cc8d8c7d))
* **security:** P2 内容安全变体规则+fail-closed + 权重SHA256校验接线 + 训练operation_id ([3c095ac](https://github.com/ReSerendipity/TTS_MultiModel/commit/3c095ace57c1652a9ac05225624e7427d44fadab))
* **security:** 二进制/模型权重完整性校验默认接线 (C1/M8/M1) ([01e7e70](https://github.com/ReSerendipity/TTS_MultiModel/commit/01e7e70f90b4ab4f052bd048f9224312d56300ca))
* **security:** 内容安全网关受配置开关控制 + 拦截审计 (M3) ([f7cbcf0](https://github.com/ReSerendipity/TTS_MultiModel/commit/f7cbcf081698a830ca3de7086564b3faca395664))
* **security:** 历史记录 PII 字段级加密落库与留存清理 (H3) ([d818f62](https://github.com/ReSerendipity/TTS_MultiModel/commit/d818f62dc5fefc8bbf0fd131c19b7cdba5a5e895))
* **security:** 路径遍历防护/LoRA白名单/模型注册完整性/路由鉴权 ([cb11bf5](https://github.com/ReSerendipity/TTS_MultiModel/commit/cb11bf5385f8c3f954c5cefd6d40bbacb7f6e969))
* **security:** 速率限制覆盖 /v1 与上传端点 + 可信代理 XFF (M2) ([1a21a72](https://github.com/ReSerendipity/TTS_MultiModel/commit/1a21a7261f4b0eb194db4847141b1450a87198f7))
* **security:** 配置模型扩展 — SSL/PII加密/审计/完整性/限流/SecretStr ([f63438c](https://github.com/ReSerendipity/TTS_MultiModel/commit/f63438c15ad8aafde4956004170c971d5b202d73))
* **task_queue:** add PerEngineQueueManager for multi-engine parallel inference ([3b083ca](https://github.com/ReSerendipity/TTS_MultiModel/commit/3b083ca3c0ca48050b7bc1fa140b5dde7cfaa7d1))
* **tests:** 安全测试补盲与 M1 里程碑达成（最终轮次） ([b6b5e48](https://github.com/ReSerendipity/TTS_MultiModel/commit/b6b5e4872e3f547ea8df7d7319cd4072fd106140))
* **tests:** 新增安全测试覆盖与引擎协议合规性测试 (M1 里程碑) ([4a2c010](https://github.com/ReSerendipity/TTS_MultiModel/commit/4a2c010cf46d47fc33a4207e3ba6e25311fc2433))
* **text-processing:** G2P manager, text segmenter, content safety, prompt expander ([9f005b8](https://github.com/ReSerendipity/TTS_MultiModel/commit/9f005b8ec5a8acab7c412a47ad17900fd0963421))
* **training:** 修复 LoRA 训练工具链 + 生成模型权重 SHA256 完整性清单 ([95ea7e9](https://github.com/ReSerendipity/TTS_MultiModel/commit/95ea7e9cb8926a6fd13e4ccc9d1178375010b15b))
* **training:** 训练启动前显存仲裁 + 自动卸载推理引擎 ([a934975](https://github.com/ReSerendipity/TTS_MultiModel/commit/a934975a33021cb49bc35f62713a535b9f87e57f))
* UI overhaul, new modules, and project cleanup ([8fbdb5f](https://github.com/ReSerendipity/TTS_MultiModel/commit/8fbdb5ff8f748e7220803aaf92cd5ac260052208))
* UI/UX audit fixes, bad-case retry queue, model optimizer, and engine refinements ([d420d15](https://github.com/ReSerendipity/TTS_MultiModel/commit/d420d1586b53a777baecce5c819739f48cd93946))
* **ui:** collapsible advanced-params panels for gptsovits/dotstts clone tabs ([05afa15](https://github.com/ReSerendipity/TTS_MultiModel/commit/05afa1544513837fd3b13b31c11e20ed3b04109b))
* **ui:** 模型切换器/语音创建表单/健康监控与样式增强；后端路由支撑 ([#62](https://github.com/ReSerendipity/TTS_MultiModel/issues/62)) ([eafc4d6](https://github.com/ReSerendipity/TTS_MultiModel/commit/eafc4d6577a0cfea3de829244d569ad0e938682e))
* update integrated app features and clean up deprecated components ([c0728cd](https://github.com/ReSerendipity/TTS_MultiModel/commit/c0728cda58111a67fe6a0902d0e55a624a661e86))
* **web:** favicon 独立资源化——icons/app-icon.svg + favicon.ico，base.html 挂接双图标 ([0c800cd](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c800cde2a92dfd81ab60c14ffeb202d2e4effe4))
* 下载指南/设置页增强 + CI 门禁收紧延续（mypy 基线棘轮）+ 引擎检查 venv 自动切换 ([e9d35cf](https://github.com/ReSerendipity/TTS_MultiModel/commit/e9d35cf1ceaaaddfef9df4745baaa38860dac7df))
* 添加性能监控脚本与计划文档 ([91b8ddd](https://github.com/ReSerendipity/TTS_MultiModel/commit/91b8ddde5dd9bb547b7bf4d0b72c9726280ed015))
* 累计提交历史任务成果 - IndexTTS2 引擎完善/多语言/文档/学习报告 ([36a94f2](https://github.com/ReSerendipity/TTS_MultiModel/commit/36a94f29cd3040c4489670e07c22f25762109ddf))
* 跨项目借鉴改造 — 安全/配置/断点续跑/模型共享/音频水印 ([11a0e57](https://github.com/ReSerendipity/TTS_MultiModel/commit/11a0e57ea5d887e272c24563ab84f9883945686c))
* 路线图落地 — 数字水印、spec 契约层、断点续跑恢复接线、前端冒烟 ([27e2a7d](https://github.com/ReSerendipity/TTS_MultiModel/commit/27e2a7dc0d236bd3cd4b350e315ae2ad478650d1))


### Bug Fixes

* .gitignore static/ 规则过宽导致前端资源未入库（CI 页面无 CSS/JS）；锚定根目录并补提交 static 39 个文件 ([fc9c484](https://github.com/ReSerendipity/TTS_MultiModel/commit/fc9c484899839cca12a138f60b9e4895ce44699e))
* **api,ui:** resolve persona API 404 and 11 UI issues ([a18f0a2](https://github.com/ReSerendipity/TTS_MultiModel/commit/a18f0a2b4a65a94ccbd12b462557e591975e866c))
* **api:** 前后端一致性 P0/P1 后端修复——参数接线与死参清理 ([a0769c6](https://github.com/ReSerendipity/TTS_MultiModel/commit/a0769c68b817532a4639c22c399450b5dfbaeed3))
* app_server 补充 __main__ 入口（python -m 启动失败根因，E2E 服务器无法启动） ([611422c](https://github.com/ReSerendipity/TTS_MultiModel/commit/611422c3c8c7817e21a071f95c0f79ba8eb1b3ff))
* **build:** 移除 license classifier（PEP 639 与 license 表达式冲突，新版 setuptools 拒绝构建） ([aca3fc7](https://github.com/ReSerendipity/TTS_MultiModel/commit/aca3fc71a1e8fa5d374d3338a75f6140cd074ccb))
* check_local.py 移除未使用 import 并通过 black ([8834c15](https://github.com/ReSerendipity/TTS_MultiModel/commit/8834c15605db4853ac611a97537c1a58237152a5))
* **ci:** .gitignore 的 model/ 误吞 upstream 源码，修复 CI 幻影导入报红 ([3258e4e](https://github.com/ReSerendipity/TTS_MultiModel/commit/3258e4eca5412fa70b75fc9200670814c0b06ee9))
* **ci+tests:** 修复流水线、激活 smoke marker 并更新 AGENTS.md ([89bbcdd](https://github.com/ReSerendipity/TTS_MultiModel/commit/89bbcdd023b37e70dae76afe0af4b5a3352a2716))
* **ci:** coverage omit */vendor/*（分母回归、pytest 覆盖率门禁有效）+ docker-build 构建后清缓存再扫描（runner 磁盘耗尽修复） ([65077f2](https://github.com/ReSerendipity/TTS_MultiModel/commit/65077f20a9a63845db08ba320b066db62e763145))
* **ci:** DCO check via self-contained bash (dcoapp/dco is a GitHub App, not an Action) ([c67a0ff](https://github.com/ReSerendipity/TTS_MultiModel/commit/c67a0ff67480429d225d5cd1ce8de139a1939905))
* **ci:** mypy 基线 101→103（M4/M5 容器安全批次新增 2 处类型债务，watermark bytearray→bytes 真修复已含） ([f6fde3d](https://github.com/ReSerendipity/TTS_MultiModel/commit/f6fde3d816d2ad6c4377d31eda82c1112cb627a1))
* **ci:** pytest 加 180s 超时保护（pytest-timeout），防止测试挂起导致 job 卡 6 小时 ([e47fe7b](https://github.com/ReSerendipity/TTS_MultiModel/commit/e47fe7b05851f64b59550fe04e2a614a6d0f9d42))
* **ci:** release-please 三处静默失效——它其实从没发过版（merge 需等 v2.2.2 tag 落地） ([a174a2e](https://github.com/ReSerendipity/TTS_MultiModel/commit/a174a2e5025d6eb128ddf0949282747c6fc76178))
* **ci:** release-please 改为仅手动触发（避免 push 时误报失败） ([2676fe2](https://github.com/ReSerendipity/TTS_MultiModel/commit/2676fe286e8e8ec9c855a5839d132a3c82e1212a))
* **ci:** render_pages 自建最小 Jinja2 环境，修复 Frontend Smoke 红灯 ([a79d581](https://github.com/ReSerendipity/TTS_MultiModel/commit/a79d58120949647919a1e1c19f859b075c68b2ed))
* **ci:** watermark metadata 类型注解（棘轮 100≤101）+ trivy-action SHA pin v0.36.0 + md5 usedforsecurity=False（bandit B324） ([0c9bd5b](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c9bd5b93956099b5309f8f603d9528ed4fc12aa))
* **ci:** 为 docker-publish.yml 的 Trivy 扫描设置 10m 超时 ([d246704](https://github.com/ReSerendipity/TTS_MultiModel/commit/d246704cf1ecd3882050151ce9076063f58a4ee9))
* **ci:** 为 Trivy 扫描设置 10m 超时，避免大镜像分析触发 5m 默认上限 ([af351fe](https://github.com/ReSerendipity/TTS_MultiModel/commit/af351fe2364800edc70ed21776f808d4880f07ef))
* **ci:** 修复两个 Docker 工作流的 Trivy 扫描假红 ([ee3ec76](https://github.com/ReSerendipity/TTS_MultiModel/commit/ee3ec761bcc956f8efed93842d2b98c0a6c2d433))
* **ci:** 修复被前置门禁遮蔽的下游红灯（引擎规格门禁 / compose schema / 完整性清单） ([11abb15](https://github.com/ReSerendipity/TTS_MultiModel/commit/11abb154892e2915467fd9a8788aec064f84b09c))
* **ci:** 修复配置门禁红灯与 Docker 构建 ensurepip 缺失 ([e6442df](https://github.com/ReSerendipity/TTS_MultiModel/commit/e6442df9db637cf7122c8e7fcaaddf964824b9d5))
* **ci:** 压力测试安装 pytest-timeout，修复 --timeout=300 无法识别 ([08003f5](https://github.com/ReSerendipity/TTS_MultiModel/commit/08003f5a67a5f982d24de9eb3c3737e237158a58))
* **ci:** 把 release-please 从"永远绿的空转"修成真会发版（含两个静默失效点） ([6396bcb](https://github.com/ReSerendipity/TTS_MultiModel/commit/6396bcbda184bc37493a6de55e102dbc95d8eeb6))
* **ci:** 补装训练层依赖，修复覆盖率预算门禁在 CI 结构性假红 ([a157e0f](https://github.com/ReSerendipity/TTS_MultiModel/commit/a157e0f707652a3481a74920e14acbd2e022b740))
* **compose:** 云原生评估 P1-1/P2-4/P2-6 跟进——解释器同步、停等对齐、日志格式统一 ([094d0b3](https://github.com/ReSerendipity/TTS_MultiModel/commit/094d0b39fcc66c5b01443bc83d891700b8f3c31e))
* **config:** 路由层改用类型化 AppConfig 访问，修复 mypy 棘轮回归 ([60e8dfe](https://github.com/ReSerendipity/TTS_MultiModel/commit/60e8dfe6a6d983de865265c1d7f6b9bda293dbc9))
* **consent:** 克隆授权门禁 P0-1 + 完整性清单同步 + 移除 CONTRIBUTING.md（compliance 批次） ([#68](https://github.com/ReSerendipity/TTS_MultiModel/issues/68)) ([a3d336c](https://github.com/ReSerendipity/TTS_MultiModel/commit/a3d336cd366aee5777fa94708292319012c86e60))
* **core:** 修全站 toast 静默失效与 3 处幻影引用，语言下拉标签接入 i18n ([62d8544](https://github.com/ReSerendipity/TTS_MultiModel/commit/62d85446a518b6c90d9cd38aee56ebdf6e842219))
* **deps:** einops 提为核心依赖，并把"声明了却没钉版"这一类变成门禁（镜像探针抓出来的） ([b34da43](https://github.com/ReSerendipity/TTS_MultiModel/commit/b34da43f22d28e9ff32938145791a9e875e4c943))
* **deps:** repair pydantic-core lock pair and stop Dependabot breaking it ([#92](https://github.com/ReSerendipity/TTS_MultiModel/issues/92)) ([09b7cdb](https://github.com/ReSerendipity/TTS_MultiModel/commit/09b7cdb4569bc0503e8f03659ed341595788bd17))
* **deps:** 下界回到 transformers&gt;=4.52.1,&lt;4.53，两道安全门禁改为逐条带理由的豁免 ([77ac14b](https://github.com/ReSerendipity/TTS_MultiModel/commit/77ac14b4472b77fb1210ccf14b32fadd8df23612))
* **deps:** 依赖下界回到实测能跑的 transformers 4.52.x，安全门禁改为逐条带理由的豁免 ([e4f20d3](https://github.com/ReSerendipity/TTS_MultiModel/commit/e4f20d3047f9652f351f7f6cd37031984ceb97d6))
* **deps:** 把"下界 vs 引擎可用性"的互斥交回决策，本 PR 只保留无争议部分 ([a4b64f3](https://github.com/ReSerendipity/TTS_MultiModel/commit/a4b64f3efc1041ca19489d41e64e941307003100))
* **deps:** 锁集三处非法约束改为合法，并把 crossconflict 检查接进 CI ([8b5dd4c](https://github.com/ReSerendipity/TTS_MultiModel/commit/8b5dd4cd38e66951faeeea7e712d0406ebb21415))
* **deps:** 锁集三处非法约束改到合法且与已验证环境一致，并把 crossconflict 检查接进 CI ([91a0846](https://github.com/ReSerendipity/TTS_MultiModel/commit/91a0846dfc93baec35939777abe747da82c692ae))
* **dist:** 发布门禁补 ⑤ 冒烟启动与磁盘释放，闭环完整性 enforce ([48bd757](https://github.com/ReSerendipity/TTS_MultiModel/commit/48bd75714819b30092016274c741a2e1a73d2cab))
* **docker:** deadsnakes 索引没抓下来时硬停，不再两步之后炸成"Unable to locate package" ([6ebfa43](https://github.com/ReSerendipity/TTS_MultiModel/commit/6ebfa435b0475af4d5b097149bd1ec380b9213c2))
* **docker:** deadsnakes 索引没抓下来时硬停（推翻 bash-builtins 假设） ([f39bdb1](https://github.com/ReSerendipity/TTS_MultiModel/commit/f39bdb137ffa71987db88e7d46480fa2b0b7109e))
* **docker:** 云原生评估 P1-1/P2-2/P2-4 落地——镜像 Python 3.10→3.12 与可复现性加固 ([2993c22](https://github.com/ReSerendipity/TTS_MultiModel/commit/2993c227f19ce3186706bf8c7cc16c3814077050))
* **docker:** 修正容器内包导入路径与 ttsuser 的 home，容器才起得来 ([c305daf](https://github.com/ReSerendipity/TTS_MultiModel/commit/c305daf415310997a11c1bf1083b44e6e5810061))
* **docker:** 容器内 import 路径与 ttsuser home 修正（liveness 长期红的下一层） ([6046bfa](https://github.com/ReSerendipity/TTS_MultiModel/commit/6046bfa45e34155ceddb79c234d848b57959adc2))
* **docker:** 消除 pids_limit 与 deploy.resources.limits.pids 取值冲突（Docker Smoke 长期红） ([98b30a0](https://github.com/ReSerendipity/TTS_MultiModel/commit/98b30a0cbe8c09ae3751a684de30ab6da59daaae))
* **docker:** 消除 pids_limit 与 deploy.resources.limits.pids 的取值冲突 ([5d9b77f](https://github.com/ReSerendipity/TTS_MultiModel/commit/5d9b77f6939369cfc27fcb0da7b179fb69b5cbad))
* **e2e:** collapse_toggle 与 theme_toggle 测试前 dismiss onboarding overlay（CI 全新环境无 localStorage 缓存） ([87769a3](https://github.com/ReSerendipity/TTS_MultiModel/commit/87769a3166104bccc29e906563b9a5ee8e253aba))
* **e2e:** expand collapsed nav section before clicking tab in extended screenshot test ([b1b4301](https://github.com/ReSerendipity/TTS_MultiModel/commit/b1b4301a57efc3f0244d675722d7e2d270dc6691))
* **e2e:** test_collapse_toggle 完整版 onboarding dismiss（等 2.2s 覆盖 setTimeout boot + 二扫 DOM） ([590d257](https://github.com/ReSerendipity/TTS_MultiModel/commit/590d2579d28f0ece14247c3ed20e2a4200ff81a2))
* **e2e:** 修正失效的 /tabs/ 路由为 /?tab=，修复 wait_for_function arguments 兼容性（Playwright 新版） ([d58a03f](https://github.com/ReSerendipity/TTS_MultiModel/commit/d58a03f8982da3655c8e32735effa640ac3233d9))
* **e2e:** 停止 JS 定时器 + 禁用 CSS 动画消除动画帧差异；临时重建 Linux baseline ([fa50990](https://github.com/ReSerendipity/TTS_MultiModel/commit/fa509906b6eb55a69033fc185570a9d8750f25dc))
* **e2e:** 冻结 Math.random 消除波形随机绘制导致的截图差异 ([ce84dca](https://github.com/ReSerendipity/TTS_MultiModel/commit/ce84dca77c18b48bd5088a675d7e7f90748657ce))
* **e2e:** 引擎 tab 切换用 JS click 绕过 model-tabs 容器指针拦截（headless 布局差异） ([5903281](https://github.com/ReSerendipity/TTS_MultiModel/commit/5903281f62917af3c3a6147fe365e07ba230d056))
* **e2e:** 截图测试点击折叠分组内 tab 前先展开；E2E job 超时 15→30 分钟 ([c89f2dc](https://github.com/ReSerendipity/TTS_MultiModel/commit/c89f2dc879465aff635052810093d64ad5862c80))
* **e2e:** 拦截远程字体 + 等待 fonts.ready 消除字体加载时序差异 ([c34afc3](https://github.com/ReSerendipity/TTS_MultiModel/commit/c34afc3b6fae8cb3b3c6cb76a48e6624caffec4f))
* **e2e:** 视觉回归测试统一稳定化（onboarding dismiss + 渲染等待）+ 更新全部 baseline ([ad2132f](https://github.com/ReSerendipity/TTS_MultiModel/commit/ad2132f8042c37d9abad80e2b66e997df1c31c95))
* **e2e:** 等待 htmx 异步内容加载完成再截图（消除跨 run 加载时序差异） ([7359fc0](https://github.com/ReSerendipity/TTS_MultiModel/commit/7359fc023ad0232f668ed5f06956c656135a8c92))
* **engines:** 2.5/2.0 共用类的两处错误文案点名了错的变体 ([a68055b](https://github.com/ReSerendipity/TTS_MultiModel/commit/a68055be7909cdc7854b8daa718d020c9ea4b859))
* **engines:** EngineName 补齐 voicebox/step-audio-editx 并同步能力契约基线，重签完整性清单 ([ccb38ee](https://github.com/ReSerendipity/TTS_MultiModel/commit/ccb38ee7642bbf027b2d89f4bd0f75661b33452c))
* **engines:** 修正引擎规格三向漂移并新增一致性校验门禁 (S1-2/S3-2) ([c3e4dd1](https://github.com/ReSerendipity/TTS_MultiModel/commit/c3e4dd11a8e7e061a27a04da48134ca23238d1af))
* **engines:** 预热绕开串行队列与用户请求并发 → CUDA device-side assert（已定位并修） ([9e41963](https://github.com/ReSerendipity/TTS_MultiModel/commit/9e41963238d421f89945cda4e6ce753b9f73cbe5))
* **frontend,dist:** 侧栏换页竞态 + 正文字体栈，并把分发负载钉进 CI ([a654a80](https://github.com/ReSerendipity/TTS_MultiModel/commit/a654a808bc3fe9a65db3c3a7b13b6b45902135f5))
* **frontend,dist:** 侧栏换页竞态与正文字体栈，并把分发负载钉进 CI ([c9161b6](https://github.com/ReSerendipity/TTS_MultiModel/commit/c9161b61f40d87e987eda185e627542e546748d8))
* hide watermark from user-visible surfaces (logs to debug, README, demo, agreement wording) ([b1acdc5](https://github.com/ReSerendipity/TTS_MultiModel/commit/b1acdc5ad2d7b6435ddeefc31d963a64d60110e0))
* **hooks:** pre-commit 分发器支持控制台命令回退（无 venv 时框架仍生效） ([bb9c3d3](https://github.com/ReSerendipity/TTS_MultiModel/commit/bb9c3d38a49c5451207731ce7b3d2ee10ba619a0))
* **hooks:** 修正 pre-commit 配置使钩子可用 ([7bb4a73](https://github.com/ReSerendipity/TTS_MultiModel/commit/7bb4a73f82a2ff247212e981246e171f3c8d29bf))
* **i18n:** 补齐 5 语种词表至完全对齐，错误片段标题改为按端点语义可配 ([002e3cc](https://github.com/ReSerendipity/TTS_MultiModel/commit/002e3cc9cfb4382c332b3e87b733c0053dc5dce0))
* **k8s:** 云原生评估 P0-1/P0-2/P1-2/P2-6 落地——清单从'能看'变'能 apply' ([71d421c](https://github.com/ReSerendipity/TTS_MultiModel/commit/71d421ca306f9da9fdc7d3e1fec6877e92200f7a))
* **launcher:** 便携钉装自洽修复（真实构建暴露，P1-1 补正） ([5c4f485](https://github.com/ReSerendipity/TTS_MultiModel/commit/5c4f485fd8654b623546d16e3123736809195775))
* **launch:** 端口被占用时自动换端口，移除交互式强杀确认 ([04dbf2e](https://github.com/ReSerendipity/TTS_MultiModel/commit/04dbf2e8f193ffea19ffa3ee24295d3bf6145ae6))
* **model-manager:** 恢复被 lint 删除的 re-export 门面并统一 lint 范围 ([74ce0f7](https://github.com/ReSerendipity/TTS_MultiModel/commit/74ce0f7b0455668e0ae5e26cd7734f5e9c0ede28))
* **openai:** tts-1-hd 从必然 500 改成 400 + 出路；smoke 补 2.5 真合成与状态谓词修正 ([bf2ff85](https://github.com/ReSerendipity/TTS_MultiModel/commit/bf2ff859c938510e3309f9464f45b409b96ab84b))
* **portability:** 新增路径可移植性自动化检查并登记规范 ([#76](https://github.com/ReSerendipity/TTS_MultiModel/issues/76)) ([af8d3ba](https://github.com/ReSerendipity/TTS_MultiModel/commit/af8d3bacbee7db02bdd92fe9cb5db9796c3f5435))
* **portability:** 路径包含判定归一 8.3 短名，避免打包器把同目录误判为外部 ([b1eb9f5](https://github.com/ReSerendipity/TTS_MultiModel/commit/b1eb9f5079de4ba5fd13c72172979f1a062ace5a))
* **precommit:** check-engine-compat 存在 .venv 时优先用 .venv 检测，避免误用系统 python ([c771d1c](https://github.com/ReSerendipity/TTS_MultiModel/commit/c771d1ce36f5074365e7f185284b1dd8a9a25891))
* **release:** ⑤ 冒烟不再拿 fixture 的假 python.exe 当便携解释器 ([f103992](https://github.com/ReSerendipity/TTS_MultiModel/commit/f103992ac2355ad77e1a7c94280560a698c87a40))
* **release:** 修复发版链路编码崩溃与 release-please 静默空转 ([a7b7c21](https://github.com/ReSerendipity/TTS_MultiModel/commit/a7b7c2195f48cdc4184edf5492d164e439571a73))
* **release:** 发版链路编码崩溃 + v2.2.2 口径收口 + CodeQL 110 条分诊 ([552b0c6](https://github.com/ReSerendipity/TTS_MultiModel/commit/552b0c62a63d47991e3f4c3ffacd5df1a2b8e5ea))
* remove local-only Chinese docs from remote; add gitignore rules ([56e7efc](https://github.com/ReSerendipity/TTS_MultiModel/commit/56e7efc48ba271acd7b444556126d80a76aae581))
* resolve 5 better-harness findings + lint cleanup ([e04219b](https://github.com/ReSerendipity/TTS_MultiModel/commit/e04219b0792a3e680af548c0d01f8ab9f095c12e))
* resolve ruff lint & format issues to pass CI (Lint job) ([8cde27a](https://github.com/ReSerendipity/TTS_MultiModel/commit/8cde27ac738b87b555cbb928b4d1c972128b3531))
* **routes:** 运维稳定性 P1-1/P2 落地——日志端点访问控制、用户文本日志脱敏、模型路由契约全覆盖 ([85d6912](https://github.com/ReSerendipity/TTS_MultiModel/commit/85d69121a9656e7d1d56fae581b35fa9b05f085e))
* ruff import 排序（audio_watermark 拆分 import，修复 CI lint 失败） ([435c19f](https://github.com/ReSerendipity/TTS_MultiModel/commit/435c19fa62b1807f0d5fcab4f1a5d0943697dde8))
* **scripts:** pin-cross 门禁不再被一次丢包打死（顺序抓 97 个包 → 并发 + 重试） ([79b7549](https://github.com/ReSerendipity/TTS_MultiModel/commit/79b754998abfc50f9ca40d08d1af3b5a78e8c675))
* **security:** CSRF 密钥不可用时拒绝启动（清单已重生成并重签，可正常合并） ([6cb9edd](https://github.com/ReSerendipity/TTS_MultiModel/commit/6cb9edd53140beaac77506000d0fcd1a2f7ed1ab))
* **security:** CSRF 密钥拿不出来时拒绝启动，不再 warning 后无签名继续跑 ([8752729](https://github.com/ReSerendipity/TTS_MultiModel/commit/8752729e183135374eee8ed54b91c29af1dc4d09))
* **security:** CSRF 密钥按 0600 落盘，CodeQL [#1](https://github.com/ReSerendipity/TTS_MultiModel/issues/1) 走"真加固 + 有据抑制"而不是空消音 ([379905b](https://github.com/ReSerendipity/TTS_MultiModel/commit/379905b702b0e1c3a7b46fe4dbbc342021e455af))
* **security:** OpenAI 兼容端点的 voice 不再被用作文件存在性探针 ([161e78c](https://github.com/ReSerendipity/TTS_MultiModel/commit/161e78cd1b1f0f8ac80eeee8dd0643ef0bb4baf1))
* **security:** OpenAI 端点 voice 参数存在性探针 + 17 条 path-injection 复核结论 ([9c91040](https://github.com/ReSerendipity/TTS_MultiModel/commit/9c910407f23e6192f000200eeef56a3b421f1484))
* **security:** wheel 漏打完整性清单三件套，且 enforce 开着没清单时静默跳过自检 ([b6b4c7b](https://github.com/ReSerendipity/TTS_MultiModel/commit/b6b4c7b4c705885f6a25ab011cccd78099aab853))
* **security:** wheel 补齐完整性清单三件套；enforce 开着却没清单改为拒绝启动 ([0b53429](https://github.com/ReSerendipity/TTS_MultiModel/commit/0b534295429acc0d2658141d18686b68e7c8b7e3))
* **security:** 升级基础镜像系统包，修复 Trivy 发现的 14 个 HIGH CVE ([7958872](https://github.com/ReSerendipity/TTS_MultiModel/commit/7958872a519764ad2479b63e4d4b619e50a5b643))
* **security:** 封死音色嵌入读路径越界并建 CodeQL 110 条告警分诊表 ([3e910a0](https://github.com/ReSerendipity/TTS_MultiModel/commit/3e910a05c6cfe74c6c07da1538c697d560de68b6))
* **security:** 把两道门禁的豁免改成真实生效的版本，并把代价从"3 条"更正为 16 条 ([e91dae2](https://github.com/ReSerendipity/TTS_MultiModel/commit/e91dae2d3cb5b5b243ee7d202c5141b2cae1b4bb))
* **security:** 错误消息脱敏补上四条领域异常分支 ([1e29807](https://github.com/ReSerendipity/TTS_MultiModel/commit/1e298076b7f1ac6e2dc5a16ac5ce4033ec77d22e))
* **security:** 错误脱敏补上四条领域异常分支 ([970cdc2](https://github.com/ReSerendipity/TTS_MultiModel/commit/970cdc2ed223ec93f881b67a913e0f0e9ae0209d))
* **server:** SSL 显式 enabled 开关默认 HTTP + 健康 ping 统一实现 ([7b6a694](https://github.com/ReSerendipity/TTS_MultiModel/commit/7b6a6941d8f2c7f8f28109f623ecbecc933bb0a8))
* SSE 测试线程改 daemon 防 pytest 挂死（根因：SSE 无限流线程永不退出）；矩阵排除 tests/e2e（Playwright 由独立 workflow 跑） ([0c37acb](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c37acbd9d0338805365892c14d8d82bed51ba11))
* **sse:** set default retry: 3000ms for browser auto-reconnect ([ba2f0aa](https://github.com/ReSerendipity/TTS_MultiModel/commit/ba2f0aae963275f6dae0a1336ab118f8047a651b))
* **streaming:** 统一 wireGenerationResult 接线入口并新增 /api/audio 音频路由 ([#65](https://github.com/ReSerendipity/TTS_MultiModel/issues/65)) ([4924ec8](https://github.com/ReSerendipity/TTS_MultiModel/commit/4924ec83d6dae329c645415c978158fb3d792e82))
* **test:** correct whitespace and length calculation in text segmenter crossfade, fix whitespace and empty text trim in G2P manager/prompt expander, align G2P is_available with design that supported language is always available on download ([15b3f64](https://github.com/ReSerendipity/TTS_MultiModel/commit/15b3f6443f4bb8df8098056f9e598512c34cccd7))
* **test:** pretrained_models 目录测试改为自动创建（目录被 gitignore，CI checkout 不含模型目录） ([2503f0f](https://github.com/ReSerendipity/TTS_MultiModel/commit/2503f0f3141c2314b95e61623343495362c16fab))
* **tests:** 修复 EngineRegistry 导入错误 ([82f6ae5](https://github.com/ReSerendipity/TTS_MultiModel/commit/82f6ae5a37a1623fcbd864e9d8faf98a1ce0f624))
* **tests:** 修复测试反模式-PytestReturnNotNone/硬编码/残缺断言/吞没异常/视觉回归无对比, 删除废弃脚本 ([f0bcc63](https://github.com/ReSerendipity/TTS_MultiModel/commit/f0bcc63008721b98c5422c85a89596af5898d1e1))
* **tests:** 消除永真断言与零断言反模式并强化认证行为级测试 ([a982676](https://github.com/ReSerendipity/TTS_MultiModel/commit/a982676f4eb1da7677027b9e8e17d700aa375e8b))
* track docs/screenshots by fixing .gitignore glob pattern ([10ea1d2](https://github.com/ReSerendipity/TTS_MultiModel/commit/10ea1d216b0048163825cf60ee033028b6c42ec6))
* **training:** 修复 training 测试假覆盖 — datasets/argbind 可选懒加载 + 循环导入修复 ([34ebc77](https://github.com/ReSerendipity/TTS_MultiModel/commit/34ebc77a168db7367050765b475d919d87135060))
* treat dots_tts as optional in compat check; skip playwright test when dep missing ([629a1bd](https://github.com/ReSerendipity/TTS_MultiModel/commit/629a1bd76996cd6f9ee5ac85bf52c8412fd74bfd))
* **types:** mypy 棘轮 156=&gt;103 —— 修复 10 文件类型错误 ([0bd74cc](https://github.com/ReSerendipity/TTS_MultiModel/commit/0bd74cce03a0d9a0ca6ef2954f77f9119a30aa2f))
* **web:** 前后端一致性 P0/P1/P2 前端修复——控件对齐与静默失效清理 ([eea5352](https://github.com/ReSerendipity/TTS_MultiModel/commit/eea5352ba1d0dd0b4c228f881d561ceb2ecffd2f))
* zh voice warning in script dubbing play paths ([0f82d8a](https://github.com/ReSerendipity/TTS_MultiModel/commit/0f82d8abcebd7ae9ab508641306c0c386de8da79))
* zh voice warning, full-text display in continue generation to match spoken text ([b7c9f0a](https://github.com/ReSerendipity/TTS_MultiModel/commit/b7c9f0a026b3be8493d33af17806a64c50c6c8a7))
* 修复 task_queue 协程泄漏并消除测试弃用警告 ([4f1f4e0](https://github.com/ReSerendipity/TTS_MultiModel/commit/4f1f4e0bb405d6dbd9f915c1206278d76db79c66))
* 消除硬编码本机绝对路径，新增路径可移植性规范 ([#75](https://github.com/ReSerendipity/TTS_MultiModel/issues/75)) ([fc4034b](https://github.com/ReSerendipity/TTS_MultiModel/commit/fc4034b8d971fedb4fe24f2d6568420522399a9b))
* 补 psutil 依赖（health.py 顶层导入，CI 测试收集失败） ([d961d90](https://github.com/ReSerendipity/TTS_MultiModel/commit/d961d90230d33fe6809891d03c244743c07adf24))


### Reverts

* pyproject addopts 移除 --timeout（与 pytest-playwright 同名选项冲突致 visual gate 失败）；CI 命令里保留 --timeout=180 ([c2d347e](https://github.com/ReSerendipity/TTS_MultiModel/commit/c2d347e8c0e48bf544257d9ac392d200887347fb))


### Documentation

* add model download & verification examples ([0c4384f](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c4384f533ed743f9a51f4cf03772b1517e14d23))
* add module responsibility boundaries (model_manager/registry/config/service_layer/optimizer); gitignore: unify template ([1b70a86](https://github.com/ReSerendipity/TTS_MultiModel/commit/1b70a86f0ea67faff5d6813b5629450149144ccb))
* add phase-A support documentation (deps, deployment, GPU runner) ([0316275](https://github.com/ReSerendipity/TTS_MultiModel/commit/03162751a2881e99de27810b6fddf63047e83d48))
* add UI screenshots to README demo section ([3a63704](https://github.com/ReSerendipity/TTS_MultiModel/commit/3a63704399316314b9ae6c474164da9771899bb8))
* **adr:** ADR-0001 remove GPT-SoVITS + 3-engine compat checker ([5276d4c](https://github.com/ReSerendipity/TTS_MultiModel/commit/5276d4c319ea5902e92086951417203b64a939e7))
* **agents:** 家族规范审计 Phase A+B 落地 — 主干事实校正、协议 v1.11、CI 一致性 ([82c8885](https://github.com/ReSerendipity/TTS_MultiModel/commit/82c8885dc31850302e3bd23335c2895cd3df68ee))
* CHANGELOG Unreleased 补钉装自洽修复与 shebang 清理两条 ([44b4234](https://github.com/ReSerendipity/TTS_MultiModel/commit/44b4234bfd81533b4d7055dc91c019b73a955b38))
* CHANGELOG 正式跟踪 + 新增 PRIVACY_POLICY ([3bc4471](https://github.com/ReSerendipity/TTS_MultiModel/commit/3bc44717af333319a3662c3ddbfd12df1a6587ca))
* **compliance:** add independent third-party declaration vs model owners (ByteDance Seed / Alibaba Tongyi / bilibili) ([499355b](https://github.com/ReSerendipity/TTS_MultiModel/commit/499355b556b21a0b268bca4ccf9f24d4744daf8a))
* **compliance:** rebrand subtitle, unify IndexTTS version naming, add third-party disclaimer to demo footer ([61fa452](https://github.com/ReSerendipity/TTS_MultiModel/commit/61fa452cbcf2e0fe2198cd0e52ea67dbf1f8525f))
* CONTRIBUTING 脱敏后入库(对外协作指南) ([1ac53fe](https://github.com/ReSerendipity/TTS_MultiModel/commit/1ac53fe9ad29e214f4c020805a5c2d54bfbe3fd8))
* **data-governance:** 数据治理评估报告 v2.2.1（HTML 交付版）入库 ([65f1238](https://github.com/ReSerendipity/TTS_MultiModel/commit/65f1238d2cf46c37b8697bd52fea9822da7f67bb))
* **deploy:** 运维稳定性 P0 落地——K8s readiness 探针改接 /readyz 并留档冷启动 MTTR ([1862c01](https://github.com/ReSerendipity/TTS_MultiModel/commit/1862c016023de7db4d9303286db4fb6c21dbcb32))
* **DOD:** 更正镜像构建那条的记载——bash-builtins 是噪声，真因是 apt-get update 容忍索引缺失 ([39d3daf](https://github.com/ReSerendipity/TTS_MultiModel/commit/39d3daf93cb26fed791723ab294b8b0a46f38b05))
* **DOD:** 记一条发版后核对产物才暴露的缺口——wheel 未打包完整性清单，pip 路径的 enforce 从不生效 ([22f9471](https://github.com/ReSerendipity/TTS_MultiModel/commit/22f9471a681862470038a9d646ab72fc3033ed2b))
* **DOD:** 记到第几格就写到第几格 —— 补上"第二次切换后 CUDA assert"这条未定级缺陷 ([003ef9a](https://github.com/ReSerendipity/TTS_MultiModel/commit/003ef9a572301ca646fe2ad8146f815b07dd8527))
* **dod:** 记录 rebase 到 main 之后的门禁数字 ([c906b8d](https://github.com/ReSerendipity/TTS_MultiModel/commit/c906b8d9decea009f68f03408dac1f6b41b216d4))
* enhance community engagement and onboarding experience ([538cf84](https://github.com/ReSerendipity/TTS_MultiModel/commit/538cf845fd1da9694de6917f25f5200977419ca6))
* **examples:** add batch + dots.tts quickstart clone examples ([cc92efd](https://github.com/ReSerendipity/TTS_MultiModel/commit/cc92efd5ca52ea7328b7540e5e11491a6765fc43))
* **governance:** 家族规范治理 Phase C/D/E 落地 — 一致性、补齐与账本 ([6e4afea](https://github.com/ReSerendipity/TTS_MultiModel/commit/6e4afeaaf1ad55443a4144bb798b0d57a7200c96))
* link MODEL_DOWNLOADS.md from README ([93bc422](https://github.com/ReSerendipity/TTS_MultiModel/commit/93bc4223a3c3e06f7d35a1ba256fccdec8cf5ce7))
* pending issues tracker + security + training guide ([deb4c06](https://github.com/ReSerendipity/TTS_MultiModel/commit/deb4c0690d0a7543f7a437e42365be60bca825f9))
* **plan,stage-e:** execution handbook for 6 task packages (5 sub + PWA skip) ([d379a71](https://github.com/ReSerendipity/TTS_MultiModel/commit/d379a717229782ad2e782725addbdbc30bce9f17))
* **quality,stage-e:** baseline quality report + reproducible evidence ([a9cd539](https://github.com/ReSerendipity/TTS_MultiModel/commit/a9cd53973b95b1f0fab8850b1ea97eac8de51a28))
* **readme:** Demo 段接上真实存在的 6 张界面截图 ([89b909f](https://github.com/ReSerendipity/TTS_MultiModel/commit/89b909ff37841266a94dc6844ecb055e3abfe955))
* **readme:** Docker 部署补充 GHCR 镜像拉取（对齐已有发布） ([bddfe4f](https://github.com/ReSerendipity/TTS_MultiModel/commit/bddfe4f85a6165dbc90e5f31fdc725fdb9fdc899))
* **readme:** 修正 GHCR 镜像 tag 为最新已发布版本 ([6401c61](https://github.com/ReSerendipity/TTS_MultiModel/commit/6401c61992e8db4a59938ceb26a751595375cbab))
* **readme:** 公开仓库向重写（五引擎定位、API 与许可表对齐） ([ddb8927](https://github.com/ReSerendipity/TTS_MultiModel/commit/ddb8927de3db730239aa724b93065f575c48fa46))
* record watermark v2 known boundaries (1s-white-noise payload info-theoretic limit, SNR-crest coupling) with measured data and optional breakthrough paths ([fc2585f](https://github.com/ReSerendipity/TTS_MultiModel/commit/fc2585febd45cc7f9ea1609847bbaba700f05d74))
* refresh README + recapture all tab screenshots (light + dark) ([d6ff151](https://github.com/ReSerendipity/TTS_MultiModel/commit/d6ff151643048f97d6b581971cceab7a5ed261ba))
* relicense from MIT to Apache License 2.0 ([5ab840b](https://github.com/ReSerendipity/TTS_MultiModel/commit/5ab840b714e09a9c80881fa0399ddaa6e31f92e2))
* remove dots.tts references and add VoxCPM source baseline ([c24ec79](https://github.com/ReSerendipity/TTS_MultiModel/commit/c24ec79ba7c1087a707ef49f967aceda1ecfb309))
* restore open-source essentials (LICENSE, NOTICE, USER_AGREEMENT, COC, SECURITY, upstream source declaration) ([dea71ee](https://github.com/ReSerendipity/TTS_MultiModel/commit/dea71ee78c4d83b9c86af860f53ebd24f530cc74))
* restore README, CI, demo, screenshots to remote; gitignore local-only content; restore pyproject readme ref ([2816758](https://github.com/ReSerendipity/TTS_MultiModel/commit/28167584e6e51d2aa0d223cb33deeb1c3930a3cc))
* restore README, CI, demo, screenshots to remote; restore pyproject; gitignore local-only ([4bbcdf8](https://github.com/ReSerendipity/TTS_MultiModel/commit/4bbcdf8555f081be411af7c0fa9c02b7b7a9cb4a))
* **roadmap,stage-e:** E.1-E.5 sub-tasks planning + PWA feasibility study ([2c4b666](https://github.com/ReSerendipity/TTS_MultiModel/commit/2c4b666932bf446b7bf0f6c6e4dcf7e123a4d61e))
* **security:** §5 补上 dismissal 的合法枚举与 20 条告警的逐条处置映射 ([eae5134](https://github.com/ReSerendipity/TTS_MultiModel/commit/eae5134a49c9af8ec3decd1047d7b0cc747bd832))
* **security:** 20 条告警 dismiss 的执行记录 + 三条实测 API 行为（PATCH / 280 字上限 / 409） ([0f59891](https://github.com/ReSerendipity/TTS_MultiModel/commit/0f59891bd400f22847fdb708fc69539d4574ea29))
* **security:** 20 条告警的 dismiss 已执行完毕，并记下三条只有实测才知道的 API 行为 ([a799620](https://github.com/ReSerendipity/TTS_MultiModel/commit/a799620ec10c20299ce621bcf48001773f71f144))
* **security:** P3 新建根级 SECURITY.md，修复 docs/SECURITY.md 断链 ([1fb861b](https://github.com/ReSerendipity/TTS_MultiModel/commit/1fb861b86c17fbd21e42bb5e0e8bb23df40309f0))
* **security:** protobuf 上界改为实测结论（无人挡住）+ 锁集全量审计数字 ([1b29d0f](https://github.com/ReSerendipity/TTS_MultiModel/commit/1b29d0ff31dd3b8e741f927abbfb3eaa1d93e58c))
* **security:** protobuf 的"上界来源"改为实测结论（没人挡住），并补锁集全量审计数字 ([a185ebc](https://github.com/ReSerendipity/TTS_MultiModel/commit/a185ebc46f15e4ee9c7011e7512480535f48ea7b))
* **security:** 云原生评估证据绑定整改——修复安全架构章节路径漂移 ([9a2445b](https://github.com/ReSerendipity/TTS_MultiModel/commit/9a2445b3de37c6a57edb178d75b343bedf1be323))
* **security:** 把 CodeQL 分诊台账从 PR [#81](https://github.com/ReSerendipity/TTS_MultiModel/issues/81) 里救出来，并按 09-21 实测刷新到 76 条 ([b179a7f](https://github.com/ReSerendipity/TTS_MultiModel/commit/b179a7f23a38adb8bfa0b6e941978eaeee7d8601))
* **security:** 救回 CodeQL 分诊台账并按 09-21 实测刷新（open 110→76，critical 归零） ([5753fbd](https://github.com/ReSerendipity/TTS_MultiModel/commit/5753fbd95c40349835e35c2b6d8a5c1dc65f9336))
* self-check pass, bump v1.7 ([ac8e7c1](https://github.com/ReSerendipity/TTS_MultiModel/commit/ac8e7c11da1c4ff0d234a579ffc291b25d4fecf0))
* **service-layer:** 记录 HTTP 生成路由迁移至 service_layer 的阻塞分析 (S2-4) ([26d584b](https://github.com/ReSerendipity/TTS_MultiModel/commit/26d584b0253099d2d9e7f0f2959d583a514d3289))
* **sync:** synchronize 3-engine governance completion state ([706d3c2](https://github.com/ReSerendipity/TTS_MultiModel/commit/706d3c2eb3b3e688afd83b71df25bd27bacc8daf))
* tasks index and v2 workflow - 8 chapters + 2 appendices, maintained on task completion ([63b2cf8](https://github.com/ReSerendipity/TTS_MultiModel/commit/63b2cf8b6dfb2649b68ed47ce4c9a3a26b04a043))
* trigger pages deploy ([f42a806](https://github.com/ReSerendipity/TTS_MultiModel/commit/f42a806e7a9c11ac4c843720ff70e132884d35d0))
* TTS_MultiModel v2.2.0 安全合规体系完整性评估与整改报告 ([03ba382](https://github.com/ReSerendipity/TTS_MultiModel/commit/03ba38296cb5efdd2e07fe243f6e097da93d1285))
* update README to include dots.tts (three-model support) and API/dirs ([c6084f8](https://github.com/ReSerendipity/TTS_MultiModel/commit/c6084f8abf31223ea920de8035d6cd011c5d3f37))
* 密钥轮换 SOP-19 runbook（演练记录：三脚本可用性已验证） ([a8823f3](https://github.com/ReSerendipity/TTS_MultiModel/commit/a8823f327974ad16bb4d56bd8091028f6a0c39da))
* 归档评估报告至 docs/_devarchive，README 补结构树，新增六大项目文档整理核对 ([6f1d241](https://github.com/ReSerendipity/TTS_MultiModel/commit/6f1d241b4615fc6725e0eae8aaca7825412b685e))
* 新增 ROADMAP.md 长期路线图 ([6311eab](https://github.com/ReSerendipity/TTS_MultiModel/commit/6311eabf1092888c82501fa45bcb7a2e1da9569b))
* 新增 TTS 竞品库技术学习报告（T5，4 份） ([9bbd381](https://github.com/ReSerendipity/TTS_MultiModel/commit/9bbd3818db902d61462a92e8cc8ef3161ff538dd))
* 新增远程同步铁律，防止 AI 直写远程后本地分叉 ([ebfabbd](https://github.com/ReSerendipity/TTS_MultiModel/commit/ebfabbd5c3b09ba3cd9eab98066bcc06951474f5))
* 桌面分发与安全加固 P0-P2 落地同步（CHANGELOG Unreleased） ([2b877bf](https://github.com/ReSerendipity/TTS_MultiModel/commit/2b877bfd4e6ca8ee4a9f40178195a92db22be66f))
* 模型下载章节补充 HuggingFace/ModelScope 链接，新增社交预览图 ([19cb124](https://github.com/ReSerendipity/TTS_MultiModel/commit/19cb124bf246f355b6adf87e393dde261746e4a8))
* 治理执行总结入库（钩子四级回退 / 日志落点 / 约定速查） ([7ebde50](https://github.com/ReSerendipity/TTS_MultiModel/commit/7ebde50170f7782414dce440cad6305cd72e1bab))
* 界面预览只展示浅色截图，深色截图不再跟踪 ([2a7b926](https://github.com/ReSerendipity/TTS_MultiModel/commit/2a7b9268881f971f9d6b92e89db1f96c055f2ff7))
* 统一安全披露渠道并对齐 version.json 发布日期 ([#66](https://github.com/ReSerendipity/TTS_MultiModel/issues/66)) ([3be35aa](https://github.com/ReSerendipity/TTS_MultiModel/commit/3be35aa8f3b9f113f4214c5d84e8d1097d6b89cc))
* 补全项目健康度评估报告全部缺失要素（perf目录+AGENTS.md+ARCHITECTURE.md+pre-commit） ([a5348c2](https://github.com/ReSerendipity/TTS_MultiModel/commit/a5348c2f5481f43752cef31c1dc7bafe0efa8247))
* 顶部补齐 CI 徽章，移除底部重复徽章 ([1205d8a](https://github.com/ReSerendipity/TTS_MultiModel/commit/1205d8a76c9f68d0653a0ddee9a847ffeb8893a2))

## [Unreleased]

## [2.2.3] - 2026-09-22

补丁版，只为把一处**随包分发缺口**送进可安装的产物：它修在 main 上，但晚于 v2.2.2 的 tag，
所以 v2.2.2 的 wheel 里仍然带着这个缺陷。

### Security

* **integrity:** wheel 此前**没把完整性自检三件套打进包**（`integrity_manifest.json`、其
  `Ed25519` 签名、验签公钥），而 `config.yaml` 默认 `security.integrity_selfcheck.enforce: true`，
  且"清单不存在"分支只 `logger.info("跳过自检")` 就返回 → **纯 `pip install` 的部署路径上
  P0 完整性保护一条都没执行，配置却声称它在强制运行**（Docker 与便携包另外拷了源码树，
  所以容器启动探测一直是绿的，把这个缺口遮住了）。现在三件随包走，且 enforce 开着却没清单
  → `RuntimeError` 拒绝启动并给三条出路；非强制模式保持原跳过语义。验收落在**产物**而非声明：
  包内条目 1062 → 1065，并把 wheel 解到临时目录真跑一遍正负两向。
  守卫 `tests/test_integrity_selfcheck_packaging.py` + CI 的 `Build (sdist/wheel)` 新增产物核对步骤。

### Bug Fixes

* **ci:** `release-please.yml` 的三处静默失效已修（`skip-github-pull-request: true` 而仓库从无
  release PR → 每次 main push 都 `found 0 possible releases` 后成功；5 个 v4 不认的入参被整段忽略；
  job 从未声明 `outputs:` → 挂在它下面的 `build-release`（sdist/wheel + SHA256SUMS）永远不跑）。
  修好后它当场自动开出了下一条 release PR，故补上 `release-please-config.json` 与
  `.release-please-manifest.json`，并加"什么都没发生就硬失败/写进 job 摘要"的自证。
* **version:** 版本位一致性守卫（#113 引入）补两处：漏核了**安装器内嵌**的
  `scripts/installer/version.json`（`setup.nsi` 的 `File "version.json"` 取的就是它，且没有脚本
  会重新生成它）；另撤掉一条我自己写反的断言 —— `minimum_shell_version` 是**下界**，
  强令它等于当前版本等于每次发版把上一版壳判死，改为只要求"不高于本次版本"。

### 已知未覆盖（同 v2.2.2 口径，未变）

桌面安装包链路与便携分卷仍无 workflow 覆盖；GPU 冒烟因无注册 runner 在 CI 上恒为 skipped；
锁集的全新 venv 真装复验待执行。

## [2.2.2] - 2026-09-22

<!-- 2026-09-16 那批内容原挂在「未发布」的 v2.2.2 标题下（tag 曾建后撤销）；2026-09-22 正式发出，
     并追加「发布前置回归」一节记录 09-21/22 这一批。资产范围见本节末尾的说明。 -->

### Features

* **desktop:** Tauri 桌面壳（`desktop/src-tauri`）：完整性自检签名 + enforce、水印密钥管理、启动契约（`runtime\python.exe` + `start_portable.py`，`--port` 由壳指定）（对应《桌面分发与安全加固-20260910》P1-2）
* **dist:** 便携分卷打包（core/torch/model 三组件、1900MB 7z 原生分卷、SHA256SUMS 全覆盖 + 回读校验）、NSIS 安装器（`scripts/installer`，kill 子进程 + 许可页）、增量更新（`make_shell_update.ps1` 生成 zip + `shell-update.json` 扁平契约）、发布门禁五步（`release_gate.ps1`）与完整性逐环节诊断（`diag_integrity.py`）（对应 P1-3/P2-1）
* **desktop:** 主界面窗口控制适配——无边框壳导航到后端页面后由桥接注入自绘标题栏（拖拽/双击最大化/最小化/关闭，`window_start_dragging`/`window_is_maximized`/`window_request_close` 三新命令与权限）；splash 补最大化按钮；关闭语义与系统 X 一致（尊重 `close_to_tray`）（GOTCHAS #104）

### Bug Fixes

* **dist:** 修复 requirements-lock.txt / requirements-small.txt 与 .venv 实测的版本漂移脱节（antlr4/pydantic/pydantic-core/mpmath/protobuf/transformers/tokenizers 按实测回退），解决全新 WinPython 上 `pip install -r requirements-small.txt` 连续 ResolutionImpossible（GOTCHAS #102）
* **dist:** 修复 `release_tauri.ps1` 单卷产物 bug：`$volumes` 非数组致 `manifest.json` 的 `volume_count: null`（改为 `@()` 强制数组）；`upload-list.txt` 引用不存在的 `unpack_portable_bundle.ps1`（改回实际分发的 `unpack_desktop.ps1`）
* **dist:** 补全 TTS 桌面解包器 `scripts/unpack_desktop.ps1`（此前缺失致分卷 `unpack_helper` 悬空；移植自 SeedVR2，适配根级 `runtime\`/`TTSMultiModel.exe` 布局，UTF-8 BOM）
* **dist:** NSIS 安装器正式发布形态落地——`license.txt` 升级为「中文安装须知与用户条款（合法使用承诺/隐私声明/第三方模型商用限制/免责）+ Apache-2.0 全文」；安装前告知弹窗（磁盘/离线/AI 标识义务，静默自动确认）；修复 `assemble_installer_data.ps1` 顶层文件被 `Copy-TTSMultiModelTree` 打包成同名目录的布局错误（GOTCHAS #103）+ 安装器嵌套布局防御断言；`TTSMultiModel-Setup-v2.2.2.exe` 端到端静默安装→布局断言→VoxCPM2 引擎就绪→卸载复验全过

### Security

* **dist:** 发布物剔除本机泄漏与开发遗留——`app/cert.pem`/`app/key.pem`（本机 HTTPS 私钥曾随包分发！）与 `start_ui_test.py`/`general_settings.json`/`SHA256SUMS.known-good`/`.server_port`/`tts_test/`/egg-info 全量进排除清单，`DeniedLeafNames` 门禁补 cert/key（进包即构建失败）；发布根目录剔除 CHANGELOG/SECURITY/pyproject/requirements-lock（GOTCHAS #104）
* **integrity:** 核心模块完整性自检 Ed25519 签名 + `enforce` 阻断（P0）；水印密钥从配置文件迁出为 env/`data/.watermark_key`（P0）；便携包清单重算/重签链路（`generate_integrity_manifest.py --app-dir` + EOF 尾换行规范化）、分发负向断言（无密钥/本机路径残留）、篡改模拟门禁（P1-3/P2-1）

### Bug Fixes

* **ci:** 修复 `scripts/check_config_refs.py` 配置门禁红灯——①为 `config.yaml` 的 `watermark:` 段补建 `WatermarkConfig` 模型并挂到 `AppConfig`（`watermark.py` 长期访问未建模字段）；②把此前「只声明未消费」的 `security.training_data_ttl_days` 真正接线（新增 `cleanup_expired_training_data`，随 lifespan 周期清理与关闭清理执行）
* **docker:** runtime 阶段补装 `python3.12-venv`（Ubuntu/deadsnakes 拆分包，`ensurepip` 由它提供），修复 `python3.12 -m ensurepip --upgrade` 报 `No module named ensurepip` 导致的镜像构建失败（与 builder 阶段对齐）
* **ci:** 修复 `scripts/check_engine_specs.py` 引擎规格三向门禁在 CI 结构性不可通过——权重目录 `/model/` 已列入 `.gitignore`（外部产物、运行时卷挂载），门禁却强制要求其存在；现仓库未附带权重时磁盘存在性降级为 WARN，仅当 `model/` 已存在时才 FAIL（该门禁此前被上一道 config 门禁遮蔽，从未在 CI 跑过）
* **docker:** 修复 `docker-compose.yml` 中 `deploy.resources.limits.devices` 非法字段（Compose 规范 `limits` 仅接受 `cpus`/`memory`/`pids`，GPU 属 `reservations.devices`），该字段使 Docker Smoke 的 Compose 校验失败
* **security:** 重新生成并重签 `app/integrated_app/security/integrity_manifest.json`，使核心模块完整性清单与本批代码变更一致（否则 enforce 模式启动被拒，E2E 红）
* **ci:** 修复覆盖率预算门禁在 CI 结构性假红——`tests/training/*` 的 `skipif` 依赖 `datasets/einops/argbind/soundfile`（属 `pyproject.toml [training]` extra），而 CI 只装 `-r requirements.txt` → 训练测试整体跳过 → `training/{data,packers,state}.py` 覆盖率 0%，12 个矩阵项全部 `Check coverage budget` 失败；现三个平台的依赖安装步骤补装该 extra

### Bug Fixes

* **launcher:** 便携钉装自洽修复（真实构建暴露）——全新 WinPython 3.12.10.1 上 `pip install -r requirements-small.txt` 报 ResolutionImpossible，9 项版本对齐 .venv 实测（antlr4 4.9.3 / pydantic-core 2.46.4 / mpmath 1.3.0 / tokenizers 0.21.0 + transformers 4.52.1 / huggingface-hub 0.36.2 / protobuf 3.19.6 / fsspec 2026.6.0 / uvicorn 0.52.4），移除已不引用的 tensorboardx 钉版；92 项 dry-run 全解
* **dist:** 清理 WinPython 自带脚本 shebang 本机路径残留——`Scripts/jp.py` 首行 `#!` 硬编码构建机临时路径，被门禁 ③ no-local-path-residue 拦下；build 脚本离线验证后自动重写为 `#!python.exe`
* **dist:** 发布门禁补 ⑤ 冒烟启动——便携包解包后用包内 WPy64 python 跑 `diag_integrity.py --enforce` 自检（断言 `selfcheck=True`/`VERIFY=True`），将完整性 enforce 闭环到分发产物；④ 篡改模拟前清理 `installed`/`out-bundle` 释放磁盘（峰值 116GB→58GB）

### Chore

* **dist:** 便携依赖钉装（`launcher/requirements-small.txt` 93 项 + `torch==2.13.0+cu132` 系列钉版，`sync_requirements.py --check-small` 校验）（P1-1）

### 发布前置回归（2026-09-21/22，随 v2.2.2 发出）

* **deps（P0）:** `einops` 提为**核心依赖** —— vendored VoxCPM 在模块顶层
  `from einops import rearrange`，而它原先只出现在 `training` extra 里，`funasr`/`modelscope`
  又只在 **extras** 声明它：任何按 `requirements.txt` / `[project].dependencies` 装出来的干净环境
  （镜像、便携包）都起不来默认引擎 `tts-1`。由 docker-smoke 新增的"镜像内引擎导入探针"第一次真跑抓到
  （run 35618578940）。同形状把 `addict` 补进两份钉版集；新增守卫 D5「核心声明必须有钉版」。
* **docker:** 镜像构建间歇性失败的真因是 `apt-get update` 对「某个索引没抓下来」只打 `W:` 并**返回 0**，
  两行之后才炸成 `E: Unable to locate package python3.12`。两段 RUN 都改成「PPA 索引里真查得到才继续」，
  取不到则重试 5 轮后硬停并给可操作原因。先前记成「`bash-builtins`/man-db 的确定性故障」是**误判**，
  已被探针数据与绿色 run 双重证伪（`docs/DOD.md` 相应段落已更正）。
* **security:** CSRF 密钥取不出来时**拒绝启动**（原为 warning 后以空密钥继续挂 `CSRFMiddleware`，
  等于静默关掉这道防护）；密钥改 `0o600` 落盘、既有宽权限文件收紧；CodeQL 既有告警 #1
  （明文存储密钥）走「真加固 + sink 行带理由抑制」，不整条静音。
* **engine:** IndexTTS 推理按引擎名加 `threading.RLock`。真因是**预热绕过串行队列、与用户请求并发**
  （不是先前记的「第二次引擎切换之后」），device-side assert 会毒化整个 CUDA context 使同进程后续合成全废；
  真机并发条件下字节数与串行一致（2.5 = 336,642 B / 2.0 = 239,674 B）。
* **api:** OpenAI 口 `tts-1-hd` 不再必然 500 —— 该口没有参考音频通道，改回 400 并指明该走哪个端点。
* **ci:** 修两处「永远绿的假信号」：`gpu-smoke.yml` 的 job 因缺 secret + 零注册 runner 一直 `skipped`
  而 run 顶层 success（现发 warning 并写进 step summary）；镜像内的引擎模块此前**从没被导入过**（新增探针）。
* **deps:** 依赖下界回到实测能跑的 `transformers>=4.52.1,<4.53` + `tokenizers>=0.21.0,<0.22`；
  4.52.x 的代价按 OSV 实测是 **16 个公告**（其中 8 条上游根本没有修复版本），逐条写可达性判据与理由后
  在 pip-audit / Trivy 里绑由头豁免；20 条 Dependabot 告警同样逐条 dismiss
  （台账见 `docs/SECURITY_DEPENDABOT_TRIAGE.md`）。
* **security:** CodeQL 存量分诊台账救回并按 09-21 实测刷新：open **110 → 76**、critical **1 → 0**，
  34 条差额逐条对上账（`docs/SECURITY_CODEQL_TRIAGE.md` §6）。

> **版本口径如实记一句**：本批含 **43 个 `feat:` 提交**却仍标 `2.2.2`（按 SemVer 应为 `2.3.0`）。
> 这是所有者的显式决定 —— 本段内容与 2026-09-16 那次被撤销的 v2.2.2 tag 属同一批，沿用该号。
> 另：仓库只有 1 个 Actions secret（`MANIFEST_SIGNING_KEY_B64`），`GPG_PRIVATE_KEY` 缺席 →
> `gpg-signed-release.yml` 只会 notice 跳过，资产不做分离签名；本次 Release 附源码包 + wheel +
> SHA256SUMS，**不含** 26 GB 便携分卷与增量包（那部分资产未获授权，命令见 `docs/release-governance.md` §2）。

## [2.2.1](https://github.com/ReSerendipity/TTS_MultiModel/compare/v2.2.0...v2.2.1) (2026-08-22)


### Bug Fixes

* **tests:** 修复 EngineRegistry 导入错误 ([82f6ae5](https://github.com/ReSerendipity/TTS_MultiModel/commit/82f6ae5a37a1623fcbd864e9d8faf98a1ce0f624))


### Documentation

* 顶部补齐 CI 徽章，移除底部重复徽章 ([1205d8a](https://github.com/ReSerendipity/TTS_MultiModel/commit/1205d8a76c9f68d0653a0ddee9a847ffeb8893a2))

### Chore

* **working-tree batch (uncommitted):** ruff 终检 11→0（批次内 23 文件全绿）：修复 `lora.py` F821（`LoRAMeta` 新增字段误读 `meta_dict`→`raw_meta`）、`training.py` SIM105×2、`clean_launch.py` UP009/UP015；清理 `metrics.py` 未用导入（F401）；安全/后端/容器化评估整改批次收尾，AGENTS.md 自进化同步至 v1.19（见 `docs/project/KNOWN_GOTCHAS.md` #41）

## [2.2.0](https://github.com/ReSerendipity/TTS_MultiModel/compare/v2.1.0...v2.2.0) (2026-08-21)


### Features

* add GitHub Pages online demo (pure frontend simulation) ([dad34bc](https://github.com/ReSerendipity/TTS_MultiModel/commit/dad34bcb2109be7e5936f5e58a50e01bf69f849d))
* **compliance:** add script workshop legal warning (5 locales) - prohibit synthesizing protected voices per IndexTTS DISCLAIMER ([4ae3cbd](https://github.com/ReSerendipity/TTS_MultiModel/commit/4ae3cbd1429db235701f37516240a0f8aca0e91c))
* full-feature demo v2 - 15 tabs/command palette/persona/history ([fef46c1](https://github.com/ReSerendipity/TTS_MultiModel/commit/fef46c13ff7826680dde2a5cfc3d767a18b5d1f7))
* **logging:** 完善日志机制 - 统一格式(PID/TID/模块位置/request_id) + 环境变量覆盖 + 双通道输出 ([9097178](https://github.com/ReSerendipity/TTS_MultiModel/commit/9097178276570fc9662eee3553dcb75ae0e4c54b))
* **security:** complete security hardening based on assessment report ([f623304](https://github.com/ReSerendipity/TTS_MultiModel/commit/f62330493b9732bdd17ac5387917533d00ea3969))
* **tests:** 安全测试补盲与 M1 里程碑达成（最终轮次） ([b6b5e48](https://github.com/ReSerendipity/TTS_MultiModel/commit/b6b5e4872e3f547ea8df7d7319cd4072fd106140))
* **tests:** 新增安全测试覆盖与引擎协议合规性测试 (M1 里程碑) ([4a2c010](https://github.com/ReSerendipity/TTS_MultiModel/commit/4a2c010cf46d47fc33a4207e3ba6e25311fc2433))
* **text-processing:** G2P manager, text segmenter, content safety, prompt expander ([9f005b8](https://github.com/ReSerendipity/TTS_MultiModel/commit/9f005b8ec5a8acab7c412a47ad17900fd0963421))
* update integrated app features and clean up deprecated components ([c0728cd](https://github.com/ReSerendipity/TTS_MultiModel/commit/c0728cda58111a67fe6a0902d0e55a624a661e86))
* 添加性能监控脚本与计划文档 ([91b8ddd](https://github.com/ReSerendipity/TTS_MultiModel/commit/91b8ddde5dd9bb547b7bf4d0b72c9726280ed015))
* 累计提交历史任务成果 - IndexTTS2 引擎完善/多语言/文档/学习报告 ([36a94f2](https://github.com/ReSerendipity/TTS_MultiModel/commit/36a94f29cd3040c4489670e07c22f25762109ddf))
* 跨项目借鉴改造 — 安全/配置/断点续跑/模型共享/音频水印 ([11a0e57](https://github.com/ReSerendipity/TTS_MultiModel/commit/11a0e57ea5d887e272c24563ab84f9883945686c))
* 路线图落地 — 数字水印、spec 契约层、断点续跑恢复接线、前端冒烟 ([27e2a7d](https://github.com/ReSerendipity/TTS_MultiModel/commit/27e2a7dc0d236bd3cd4b350e315ae2ad478650d1))


### Bug Fixes

* .gitignore static/ 规则过宽导致前端资源未入库（CI 页面无 CSS/JS）；锚定根目录并补提交 static 39 个文件 ([fc9c484](https://github.com/ReSerendipity/TTS_MultiModel/commit/fc9c484899839cca12a138f60b9e4895ce44699e))
* app_server 补充 __main__ 入口（python -m 启动失败根因，E2E 服务器无法启动） ([611422c](https://github.com/ReSerendipity/TTS_MultiModel/commit/611422c3c8c7817e21a071f95c0f79ba8eb1b3ff))
* **build:** 移除 license classifier（PEP 639 与 license 表达式冲突，新版 setuptools 拒绝构建） ([aca3fc7](https://github.com/ReSerendipity/TTS_MultiModel/commit/aca3fc71a1e8fa5d374d3338a75f6140cd074ccb))
* check_local.py 移除未使用 import 并通过 black ([8834c15](https://github.com/ReSerendipity/TTS_MultiModel/commit/8834c15605db4853ac611a97537c1a58237152a5))
* **ci+tests:** 修复流水线、激活 smoke marker 并更新 AGENTS.md ([89bbcdd](https://github.com/ReSerendipity/TTS_MultiModel/commit/89bbcdd023b37e70dae76afe0af4b5a3352a2716))
* **ci:** pytest 加 180s 超时保护（pytest-timeout），防止测试挂起导致 job 卡 6 小时 ([e47fe7b](https://github.com/ReSerendipity/TTS_MultiModel/commit/e47fe7b05851f64b59550fe04e2a614a6d0f9d42))
* **ci:** release-please 改为仅手动触发（避免 push 时误报失败） ([2676fe2](https://github.com/ReSerendipity/TTS_MultiModel/commit/2676fe286e8e8ec9c855a5839d132a3c82e1212a))
* **e2e:** collapse_toggle 与 theme_toggle 测试前 dismiss onboarding overlay（CI 全新环境无 localStorage 缓存） ([87769a3](https://github.com/ReSerendipity/TTS_MultiModel/commit/87769a3166104bccc29e906563b9a5ee8e253aba))
* **e2e:** test_collapse_toggle 完整版 onboarding dismiss（等 2.2s 覆盖 setTimeout boot + 二扫 DOM） ([590d257](https://github.com/ReSerendipity/TTS_MultiModel/commit/590d2579d28f0ece14247c3ed20e2a4200ff81a2))
* **e2e:** 修正失效的 /tabs/ 路由为 /?tab=，修复 wait_for_function arguments 兼容性（Playwright 新版） ([d58a03f](https://github.com/ReSerendipity/TTS_MultiModel/commit/d58a03f8982da3655c8e32735effa640ac3233d9))
* **e2e:** 停止 JS 定时器 + 禁用 CSS 动画消除动画帧差异；临时重建 Linux baseline ([fa50990](https://github.com/ReSerendipity/TTS_MultiModel/commit/fa509906b6eb55a69033fc185570a9d8750f25dc))
* **e2e:** 冻结 Math.random 消除波形随机绘制导致的截图差异 ([ce84dca](https://github.com/ReSerendipity/TTS_MultiModel/commit/ce84dca77c18b48bd5088a675d7e7f90748657ce))
* **e2e:** 引擎 tab 切换用 JS click 绕过 model-tabs 容器指针拦截（headless 布局差异） ([5903281](https://github.com/ReSerendipity/TTS_MultiModel/commit/5903281f62917af3c3a6147fe365e07ba230d056))
* **e2e:** 截图测试点击折叠分组内 tab 前先展开；E2E job 超时 15→30 分钟 ([c89f2dc](https://github.com/ReSerendipity/TTS_MultiModel/commit/c89f2dc879465aff635052810093d64ad5862c80))
* **e2e:** 拦截远程字体 + 等待 fonts.ready 消除字体加载时序差异 ([c34afc3](https://github.com/ReSerendipity/TTS_MultiModel/commit/c34afc3b6fae8cb3b3c6cb76a48e6624caffec4f))
* **e2e:** 视觉回归测试统一稳定化（onboarding dismiss + 渲染等待）+ 更新全部 baseline ([ad2132f](https://github.com/ReSerendipity/TTS_MultiModel/commit/ad2132f8042c37d9abad80e2b66e997df1c31c95))
* **e2e:** 等待 htmx 异步内容加载完成再截图（消除跨 run 加载时序差异） ([7359fc0](https://github.com/ReSerendipity/TTS_MultiModel/commit/7359fc023ad0232f668ed5f06956c656135a8c92))
* hide watermark from user-visible surfaces (logs to debug, README, demo, agreement wording) ([b1acdc5](https://github.com/ReSerendipity/TTS_MultiModel/commit/b1acdc5ad2d7b6435ddeefc31d963a64d60110e0))
* remove local-only Chinese docs from remote; add gitignore rules ([56e7efc](https://github.com/ReSerendipity/TTS_MultiModel/commit/56e7efc48ba271acd7b444556126d80a76aae581))
* resolve ruff lint & format issues to pass CI (Lint job) ([8cde27a](https://github.com/ReSerendipity/TTS_MultiModel/commit/8cde27ac738b87b555cbb928b4d1c972128b3531))
* ruff import 排序（audio_watermark 拆分 import，修复 CI lint 失败） ([435c19f](https://github.com/ReSerendipity/TTS_MultiModel/commit/435c19fa62b1807f0d5fcab4f1a5d0943697dde8))
* SSE 测试线程改 daemon 防 pytest 挂死（根因：SSE 无限流线程永不退出）；矩阵排除 tests/e2e（Playwright 由独立 workflow 跑） ([0c37acb](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c37acbd9d0338805365892c14d8d82bed51ba11))
* **test:** correct whitespace and length calculation in text segmenter crossfade, fix whitespace and empty text trim in G2P manager/prompt expander, align G2P is_available with design that supported language is always available on download ([15b3f64](https://github.com/ReSerendipity/TTS_MultiModel/commit/15b3f6443f4bb8df8098056f9e598512c34cccd7))
* **test:** pretrained_models 目录测试改为自动创建（目录被 gitignore，CI checkout 不含模型目录） ([2503f0f](https://github.com/ReSerendipity/TTS_MultiModel/commit/2503f0f3141c2314b95e61623343495362c16fab))
* **tests:** 修复测试反模式-PytestReturnNotNone/硬编码/残缺断言/吞没异常/视觉回归无对比, 删除废弃脚本 ([f0bcc63](https://github.com/ReSerendipity/TTS_MultiModel/commit/f0bcc63008721b98c5422c85a89596af5898d1e1))
* **tests:** 消除永真断言与零断言反模式并强化认证行为级测试 ([a982676](https://github.com/ReSerendipity/TTS_MultiModel/commit/a982676f4eb1da7677027b9e8e17d700aa375e8b))
* treat dots_tts as optional in compat check; skip playwright test when dep missing ([629a1bd](https://github.com/ReSerendipity/TTS_MultiModel/commit/629a1bd76996cd6f9ee5ac85bf52c8412fd74bfd))
* zh voice warning in script dubbing play paths ([0f82d8a](https://github.com/ReSerendipity/TTS_MultiModel/commit/0f82d8abcebd7ae9ab508641306c0c386de8da79))
* zh voice warning, full-text display in continue generation to match spoken text ([b7c9f0a](https://github.com/ReSerendipity/TTS_MultiModel/commit/b7c9f0a026b3be8493d33af17806a64c50c6c8a7))
* 修复 task_queue 协程泄漏并消除测试弃用警告 ([4f1f4e0](https://github.com/ReSerendipity/TTS_MultiModel/commit/4f1f4e0bb405d6dbd9f915c1206278d76db79c66))
* 补 psutil 依赖（health.py 顶层导入，CI 测试收集失败） ([d961d90](https://github.com/ReSerendipity/TTS_MultiModel/commit/d961d90230d33fe6809891d03c244743c07adf24))


### Reverts

* pyproject addopts 移除 --timeout（与 pytest-playwright 同名选项冲突致 visual gate 失败）；CI 命令里保留 --timeout=180 ([c2d347e](https://github.com/ReSerendipity/TTS_MultiModel/commit/c2d347e8c0e48bf544257d9ac392d200887347fb))


### Documentation

* add model download & verification examples ([0c4384f](https://github.com/ReSerendipity/TTS_MultiModel/commit/0c4384f533ed743f9a51f4cf03772b1517e14d23))
* add module responsibility boundaries (model_manager/registry/config/service_layer/optimizer); gitignore: unify template ([1b70a86](https://github.com/ReSerendipity/TTS_MultiModel/commit/1b70a86f0ea67faff5d6813b5629450149144ccb))
* **compliance:** add independent third-party declaration vs model owners (ByteDance Seed / Alibaba Tongyi / bilibili) ([499355b](https://github.com/ReSerendipity/TTS_MultiModel/commit/499355b556b21a0b268bca4ccf9f24d4744daf8a))
* **compliance:** rebrand subtitle, unify IndexTTS version naming, add third-party disclaimer to demo footer ([61fa452](https://github.com/ReSerendipity/TTS_MultiModel/commit/61fa452cbcf2e0fe2198cd0e52ea67dbf1f8525f))
* link MODEL_DOWNLOADS.md from README ([93bc422](https://github.com/ReSerendipity/TTS_MultiModel/commit/93bc4223a3c3e06f7d35a1ba256fccdec8cf5ce7))
* record watermark v2 known boundaries (1s-white-noise payload info-theoretic limit, SNR-crest coupling) with measured data and optional breakthrough paths ([fc2585f](https://github.com/ReSerendipity/TTS_MultiModel/commit/fc2585febd45cc7f9ea1609847bbaba700f05d74))
* remove dots.tts references and add VoxCPM source baseline ([c24ec79](https://github.com/ReSerendipity/TTS_MultiModel/commit/c24ec79ba7c1087a707ef49f967aceda1ecfb309))
* restore open-source essentials (LICENSE, NOTICE, USER_AGREEMENT, COC, SECURITY, upstream source declaration) ([dea71ee](https://github.com/ReSerendipity/TTS_MultiModel/commit/dea71ee78c4d83b9c86af860f53ebd24f530cc74))
* restore README, CI, demo, screenshots to remote; gitignore local-only content; restore pyproject readme ref ([2816758](https://github.com/ReSerendipity/TTS_MultiModel/commit/28167584e6e51d2aa0d223cb33deeb1c3930a3cc))
* restore README, CI, demo, screenshots to remote; restore pyproject; gitignore local-only ([4bbcdf8](https://github.com/ReSerendipity/TTS_MultiModel/commit/4bbcdf8555f081be411af7c0fa9c02b7b7a9cb4a))
* self-check pass, bump v1.7 ([ac8e7c1](https://github.com/ReSerendipity/TTS_MultiModel/commit/ac8e7c11da1c4ff0d234a579ffc291b25d4fecf0))
* trigger pages deploy ([f42a806](https://github.com/ReSerendipity/TTS_MultiModel/commit/f42a806e7a9c11ac4c843720ff70e132884d35d0))
* update README to include dots.tts (three-model support) and API/dirs ([c6084f8](https://github.com/ReSerendipity/TTS_MultiModel/commit/c6084f8abf31223ea920de8035d6cd011c5d3f37))
* 模型下载章节补充 HuggingFace/ModelScope 链接，新增社交预览图 ([19cb124](https://github.com/ReSerendipity/TTS_MultiModel/commit/19cb124bf246f355b6adf87e393dde261746e4a8))
* 界面预览只展示浅色截图，深色截图不再跟踪 ([2a7b926](https://github.com/ReSerendipity/TTS_MultiModel/commit/2a7b9268881f971f9d6b92e89db1f96c055f2ff7))
* 补全项目健康度评估报告全部缺失要素（perf目录+AGENTS.md+ARCHITECTURE.md+pre-commit） ([a5348c2](https://github.com/ReSerendipity/TTS_MultiModel/commit/a5348c2f5481f43752cef31c1dc7bafe0efa8247))
