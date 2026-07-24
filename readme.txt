TTS_MultiModel 全部竞品报告建议完整汇总
数据来源：reference_repos/ 下 18 个仓库 + docs/ 下 19 份技术学习报告（含综合汇总报告）
覆盖率：18/18 (100%)
一、TTS 引擎核心架构（18 个仓库涉及）
#	建议	来源仓库	优先级
1	统一引擎 Protocol 接口规范（对齐 VoiceBox 的 TTSBackend Protocol，定义 load_model/generate/create_voice_prompt/unload 标准方法签名）	VoiceBox, Coqui-TTS	P0
2	声明式模型配置注册（ModelConfig dataclass 统一管理所有引擎元数据：名称、HF 仓库、大小、语言、显存需求）	VoiceBox	P0
3	后端工厂 + 延迟实例化（线程安全双重检查锁 + 按需延迟导入引擎模块，避免启动时加载全部依赖）	VoiceBox, CosyVoice	P0
4	AutoModel 工厂模式统一引擎实例化（参考 CosyVoice 的 AutoModel.from_pretrained + 配置驱动）	CosyVoice, ChatTTS	P1
5	评估集成 GPT-SoVITS 作为第三引擎（5 秒零样本克隆 + 1 分钟微调能力，补充少样本训练短板）	GPT-SoVITS	P1
6	评估集成 CosyVoice v3 引擎（LLM + Flow Matching 架构，支持 Instruct 指令控制语言/方言/情感/语速）	CosyVoice	P2
7	评估集成 ChatTTS 引擎（双阶段 GPT + GFSQ 音频量化，对话式场景表现突出）	ChatTTS	P2
8	评估集成 Edge-TTS 作为云端降级引擎（零 GPU 占用，70+ 语言，WebSocket 流式，适用于无 GPU 环境）	Edge-TTS	P2
9	评估集成 Piper 作为轻量级边缘引擎（C++ 推理 + ONNX，CPU 实时，多质量分级 x-low/low/medium/high）	Piper	P2
10	评估集成 EmotiVoice 引擎（PromptTTS 情感控制 + JETS 联合训练，网易有道出品）	EmotiVoice	P2
11	评估集成 StyleTTS2 引擎（风格扩散 + SLM 对抗训练，达到人类水平 TTS）	StyleTTS2	P3
二、推理优化与性能（15 个仓库涉及）
#	建议	来源仓库	优先级
1	集成 RAS（Repetition Aware Sampling）采样策略（滑动窗口检测重复 token，自动提高 temperature/top_p 打破重复）	Fish Speech	P0
2	KV Cache 加速自回归推理（所有 LLM-based 引擎启用 KV Cache，prefill 阶段一次性处理输入，增量更新）	VoxCPM, Fish Speech, GPT-SoVITS	P0
3	评估 torch.compile + Triton 编译加速（VoxCPM2/Fish Speech 已验证有效，RTF 可降低 30-50%）	VoxCPM, Fish Speech	P1
4	评估 vLLM / Nano-vLLM 集成（LLM backbone 推理加速 3-5x，CosyVoice/ChatTTS/Fish Speech 已验证）	CosyVoice, ChatTTS, Fish Speech	P1
5	FP16/BF16 混合精度推理（所有引擎启用自动混合精度，精度损失 < 1%，显存减半）	所有仓库	P0
6	评估 TensorRT-LLM 加速（CosyVoice 已验证，CUDA 内核级优化，延迟最低）	CosyVoice	P2
7	评估 ONNX Runtime 推理（Piper/CosyVoice 已验证，跨平台推理优化）	Piper, CosyVoice	P2
8	评估 llama.cpp-omni 端侧推理（C++ 推理引擎，支持 CPU/Metal/CUDA/Vulkan，VoxCPM 官方生态）	VoxCPM	P2
9	串行生成队列（asyncio.Queue + Worker 模式，避免多引擎 GPU 争用，支持取消排队和崩溃恢复）	VoiceBox	P0
10	引擎切换时自动重采样（16kHz/22050Hz/24kHz/44100Hz 统一音频管线，消除采样率差异）	TTS_MultiModel	P0
11	模型格式适配器（统一 .pth/.safetensors/.onnx/.pt 加载逻辑，引擎加载层自动选择格式）	TTS_MultiModel	P1
12	显存泄漏检测增强（参考 VoxCPM 的 SIGTERM/SIGINT 信号处理 + 异常终止时自动保存检查点）	VoxCPM	P1
13	CLVP 候选排序机制（参考 Tortoise-TTS，自回归生成多个候选 → CLVP 评分选最佳）	Tortoise-TTS	P2
14	GRPO 对齐训练（参考 Fish Speech，组相对策略优化提升生成质量）	Fish Speech	P3
15	DPO 训练集成（参考 GPT-SoVITS，正负样本对比学习微调）	GPT-SoVITS	P3
三、流式处理与实时生成（12 个仓库涉及）
#	建议	来源仓库	优先级
1	流式 VAE 解码器（参考 VoxCPM StreamingVAEDecoder，修补因果卷积 padding buffer 实现增量解码）	VoxCPM	P1
2	SSE 流式推送增强（当前已实现，可参考 CosyVoice v2 双向流式架构进一步优化延迟至 150ms 级）	CosyVoice, TTS_MultiModel	P1
3	长文本智能分块 + 交叉淡入淡出（句子边界分割 → 逐块推理 → 50ms 交叉淡入淡出拼接消除 click 噪声）	VoiceBox	P0
4	逐句流式输出（按句子边界分块输出，Piper/Tortoise 已验证有效）	Piper, Tortoise-TTS	P1
5	队列化解耦异步架构（LLaMA 和 DAC 通过队列解耦，参考 Fish Speech 生产者-消费者模式）	Fish Speech	P2
6	SOLA 流式拼接（参考 GPT-SoVITS 的重叠相加算法，实现无缝流式拼接）	GPT-SoVITS	P2
7	流式 VAD 静音检测（实时检测语音段边界，动态调整分块策略）	Real-Time-Voice-Cloning	P2
8	fold_with_overlap 批量推理（参考 Real-Time-Voice-Cloning，重叠窗口提升 WaveRNN 流式质量）	Real-Time-Voice-Cloning	P3
四、音频编解码器技术（10 个仓库涉及）
#	建议	来源仓库	优先级
1	评估 AudioVAE V2 非对称编解码（16kHz 输入 → 48kHz 输出，因果卷积 + Snake 激活 + 采样率条件层）	VoxCPM	P1
2	评估 DAC（Descript Audio Codec）RVQ 替代 EnCodec（下采样残差向量量化，Fish Speech 验证更优）	Fish Speech, VoxCPM	P2
3	评估 S3Tokenizer 集成（语言无关，支持流式，Chatterbox 验证跨语言能力）	Chatterbox	P2
4	评估 Vocos 声码器（ConvNeXt + ISTFT，轻量高效，ChatTTS 验证 82M 参数 CPU 实时）	ChatTTS	P2
5	评估 BigVGAN 声码器（GPT-SoVITS v3 CFM 声码器后端）	GPT-SoVITS	P2
6	评估 HiFT-GAN/NSF+ISTFT 声码器（GPT-SoVITS v2/v4 后端）	GPT-SoVITS	P2
7	评估 UnivNet 通用声码器（Tortoise-TTS 使用，支持多种采样率）	Tortoise-TTS	P3
8	评估 WaveRNN 神经声码器（Real-Time-Voice-Cloning 使用，双层 GRU + FC，轻量级）	Real-Time-Voice-Cloning	P3
五、多语言与多说话人（12 个仓库涉及）
#	建议	来源仓库	优先级
1	集成多语言文本前端（参考 GPT-SoVITS 的 text/ 目录，支持中日英韩粤 G2P + G2PW 多音字消歧）	GPT-SoVITS	P0
2	集成 CosyVoice 文本归一化管线（数字/符号/日期/时间展开，funasr 文本处理）	CosyVoice	P1
3	自动语言检测（参考 OpenVoice/ChatTTS，输入文本自动检测语言，无需手动指定）	OpenVoice, ChatTTS	P1
4	说话人嵌入向量缓存增强（参考 Chatterbox 的条件缓存模式，预计算并持久化说话人嵌入）	Chatterbox, TTS_MultiModel	P1
5	评估 PL-BERT 文本编码器（StyleTTS2 使用，基于 BERT 的音素级别文本编码）	StyleTTS2	P2
6	评估 SimBERT 风格编码器（EmotiVoice 使用，文本→风格向量，支持情感提示）	EmotiVoice	P2
7	GE2E 说话人编码器参考（Real-Time-Voice-Cloning 经典实现，3 层 LSTM + L2 归一化 + GE2E 损失）	Real-Time-Voice-Cloning	P3
8	高斯说话人采样（ChatTTS 使用，连续音色空间采样，增加声音多样性）	ChatTTS	P3
9	评估 OpenVoice 模块化 TTS + 音色转换解耦架构（TTS + ToneColorConverter 两阶段，零样本跨语言克隆）	OpenVoice	P2
10	多说话人预设声音库（参考 Kokoro 50+ 预设声音，按语言/性别组织）	VoiceBox, Kokoro	P2
11	方言支持扩展（VoxCPM 支持 9 种中文方言：四川话、粤语、吴语、东北话等，可直接复用）	VoxCPM	P2
12	Bert-VITS2 混合语言合成（中日英三语无缝切换，WavLM 韵律建模）	Bert-VITS2	P3
六、语音克隆与零样本学习（10 个仓库涉及）
#	建议	来源仓库	优先级
1	增强 VoxCPM2 参考音频隔离机制（特殊 token 103/104 结构化隔离参考音频，loss_mask 排除参考段）	VoxCPM	P1
2	评估 Voice Design 能力（VoxCPM2 自然语言描述创建新声音：性别/年龄/语调/情感/语速）	VoxCPM	P1
3	多参考音频合并策略（参考 VoiceBox 的 combine_voice_prompts + MD5 哈希缓存合并结果）	VoiceBox	P1
4	Ultimate Clone 模式增强（参考 VoxCPM2，提供参考音频+转录文本，模型无缝延续）	VoxCPM	P2
5	MRTE 多参考音色编码器参考（GPT-SoVITS，融合多个参考音频的音色信息）	GPT-SoVITS	P2
6	CAMPPlus 说话人编码器参考（Chatterbox 使用，双说话人编码器融合）	Chatterbox	P2
7	参考音频质量预检（自动检测参考音频质量：静音比、噪声水平、时长是否充足）	Chatterbox, OpenVoice	P1
8	水印嵌入（参考 OpenVoice wavmark，生成音频嵌入不可感知水印用于版权保护）	OpenVoice	P3
9	Wav2Vec 文本对齐删减（参考 Tortoise-TTS，生成后检查文本-音频对齐，自动删减重复/遗漏）	Tortoise-TTS	P3
10	条件缓存模式（参考 Chatterbox，预计算 T3/S3Gen 条件并缓存，减少重复计算）	Chatterbox	P2
七、情感/风格/韵律控制（8 个仓库涉及）
#	建议	来源仓库	优先级
1	8 维情感向量控制（IndexTTS2 已实现：happy/angry/sad/afraid/disgusted/melancholic/surprised/calm）	IndexTTS2	P1
2	韵律 Token 系统（参考 ChatTTS 的 [laugh]/[uv_break]/[oral_0-9] 细粒度韵律控制标签）	ChatTTS	P2
3	副语言标签解析（参考 Chatterbox 的 [paralinguistic] 标签系统，支持笑声/叹息/耳语等）	Chatterbox	P2
4	Instruct 指令控制（参考 CosyVoice v3，通过自然语言指令控制语言/方言/情感/语速/音量）	CosyVoice	P2
5	风格扩散生成（参考 StyleTTS2，文本→风格向量→语音，双风格编码器 + SLM 对抗训练）	StyleTTS2	P3
6	CFG（Classifier-Free Guidance）控制（参考 Tortoise-VoxCPM，引导强度可调提升风格表达力）	Tortoise-TTS, VoxCPM	P2
7	PromptTTS 情感控制（参考 EmotiVoice，通过自然语言描述控制语音情感和风格）	EmotiVoice	P2
8	语音人格系统（参考 VoiceBox，本地 LLM 驱动角色扮演 + 文本改写，统一服务于精炼和风格化）	VoiceBox	P3
八、训练技术与微调（8 个仓库涉及）
#	建议	来源仓库	优先级
1	LoRA 微调框架优化（参考 VoxCPM 的 buffer-based scaling + torch.compile 兼容设计）	VoxCPM	P1
2	梯度累积 + 混合精度训练管线（参考 VoxCPM：BF16 + 8 步梯度累积 + AdamW + cosine scheduler）	VoxCPM	P1
3	信号处理安全保存（注册 SIGTERM/SIGINT 处理器，异常终止时自动保存检查点）	VoxCPM	P1
4	DPO 训练流程（参考 GPT-SoVITS，正负样本对比学习微调策略）	GPT-SoVITS	P2
5	GRPO 对齐训练（参考 Fish Speech，组相对策略优化替代 PPO，更稳定的对齐方法）	Fish Speech	P2
6	JETS 联合训练（参考 EmotiVoice，联合优化声学模型和声码器）	EmotiVoice	P3
7	Beta-Binomial 对齐策略（参考 EmotiVoice，改进单调对齐搜索）	EmotiVoice	P3
8	SLM（Speech Language Model）对抗训练（参考 StyleTTS2，WavLM 判别器 + TPRLS 损失）	StyleTTS2	P3
九、长文本处理（6 个仓库涉及）
#	建议	来源仓库	优先级
1	句子边界智能分割（优先级：句子结束 > 子句边界 > 空格 > 硬切，保护缩写和标签不被分割）	VoiceBox	P0
2	交叉淡入淡出拼接（50ms 淡入淡出窗口，消除拼接处 click 噪声）	VoiceBox	P0
3	种子递增策略（每块使用 seed+i 避免相关性，保持语调多样性）	VoiceBox	P1
4	CJK 标点支持（中文句号/问号/感叹号作为分句边界）	VoiceBox	P0
5	[paralinguistic] 标签保护（分块时保护韵律标签不被分割到不同块中）	VoiceBox, Chatterbox	P1
6	50,000 字符超长文本支持（参考 VoiceBox 的自动分块 + 交叉淡入淡出）	VoiceBox	P2
十、模型管理与缓存（8 个仓库涉及）
#	建议	来源仓库	优先级
1	LRU + GPU 感知自适应缓存（TTS_MultiModel 已实现 AdaptiveLRUCache，持续优化容量策略）	TTS_MultiModel	P0
2	生成版本管理系统（original → version-2 → take-N 版本链 + 来源追踪，增强用户体验）	VoiceBox	P1
3	模型预加载策略（启动时预加载常用引擎，参考 Piper 的预加载设计）	Piper	P1
4	Persona 缓存增强（参考 Chatterbox 的条件缓存 + VoiceBox 的 MD5 哈希缓存）	Chatterbox, VoiceBox	P1
5	HuggingFace Hub 本地缓存管理（参考 VoiceBox 的 hf_progress.py 下载进度跟踪）	VoiceBox	P2
6	模型版本管理（参考 GPT-SoVITS 的多版本预训练权重管理：v1/v2/v3/v4）	GPT-SoVITS	P2
7	崩溃恢复机制（启动时检查上次崩溃时的生成状态，标记为 failed 并清理）	VoiceBox	P1
8	LoRA 权重热切换（参考 VoxCPM 的 buffer-based scaling，通过 fill_() 原地修改避免重编译）	VoxCPM	P2
十一、架构 / 工程化（10 个仓库涉及）
#	建议	来源仓库	优先级
1	三层架构规范化（表现层/业务层/基础设施层分离，参考 Coqui-TTS 的 API/Model/Data 架构）	Coqui-TTS	P1
2	配置驱动开发（CosyVoice 风格，YAML 配置决定模型选择、参数、流水线）	CosyVoice, Coqui-TTS	P1
3	异步模型加载（asyncio.to_thread + Lock，避免阻塞 FastAPI 事件循环）	VoiceBox	P0
4	Pydantic 请求/响应模型规范化（参考 VoiceBox，所有 API 使用统一的 Pydantic 模型）	VoiceBox	P1
5	数据库 ORM 规范化（参考 VoiceBox 的 SQLAlchemy ORM + 迁移脚本）	VoiceBox	P2
6	服务层抽取（参考 VoiceBox，将业务逻辑从路由层分离到 services/ 目录）	VoiceBox	P2
7	统一错误处理增强（参考 VoiceBox 的崩溃恢复 + _force_fail_if_active 机制）	VoiceBox	P2
8	插件式模型扩展（参考 Coqui-TTS 的 register_config + 动态模型发现）	Coqui-TTS	P3
9	模块化测试覆盖提升（为每个引擎编写独立的单元测试和集成测试）	所有仓库	P1
10	API 文档自动生成（FastAPI 内置 OpenAPI，完善描述和示例）	TTS_MultiModel	P2
十二、音频后处理与效果（5 个仓库涉及）
#	建议	来源仓库	优先级
1	统一响度归一化（参考 Chatterbox -27 LUFS 标准，使用 pyloudnorm 实现 LUFS 响度归一化）	Chatterbox	P0
2	Pedalboard 音频效果引擎集成（8 种效果：音高变换/混响/延迟/合唱/压缩/增益/高通/低通 + 4 个预设）	VoiceBox	P1
3	响度归一化后置（所有引擎输出统一经过响度归一化，消除引擎间音量差异）	TTS_MultiModel	P0
4	VAD 静音裁切增强（参考 Real-Time-Voice-Cloning 的 WebRTC VAD mode=3 + 移动平均平滑）	Real-Time-Voice-Cloning	P2
5	音频裁剪优化（参考 VoiceBox 的 trim_tts_output，自动去除首尾静音和异常段）	VoiceBox	P1
6	ZipEnhancer 噪声抑制（参考 VoxCPM 的预处理管线，对参考音频进行声学降噪）	VoxCPM	P2
十三、API / 接口设计（6 个仓库涉及）
#	建议	来源仓库	优先级
1	OpenAI 兼容 API（参考 EmotiVoice，提供 /v1/audio/speech 端点，兼容 OpenAI SDK）	EmotiVoice	P1
2	SSE 事件流标准化（progress/complete/status/engine_switch/cancelled/time_estimate 事件类型）	TTS_MultiModel	P0
3	任务取消 API（参考 VoiceBox，支持取消排队中或运行中的生成任务）	VoiceBox	P1
4	批量生成 API（参考 batch_example.py，支持多文本批量生成 + 并发控制）	TTS_MultiModel	P2
5	生成统计 API（参考 TTS_MultiModel 的 system/health.py，暴露生成次数/平均 RTF/显存使用）	TTS_MultiModel	P2
6	Webhook 回调通知（生成完成后主动推送结果 URL，避免客户端轮询）	TTS_MultiModel	P3
十四、前端 / UI 体验（4 个仓库涉及）
#	建议	来源仓库	优先级
1	引擎选择 UI 优化（声明式配置自动渲染引擎列表，显示显存需求/支持语言/质量等级）	VoiceBox	P1
2	音频波形可视化（参考 VoiceBox 的 WaveSurfer.js 集成，实时显示生成波形）	VoiceBox	P2
3	生成进度实时反馈（SSE 推送进度百分比 + ETA，参考 VoiceBox 的 hf_progress.py）	VoiceBox, TTS_MultiModel	P1
4	多 Take 对比播放（参考 VoiceBox 的版本管理 UI，支持多版本音频对比试听）	VoiceBox	P2
十五、部署与跨平台（5 个仓库涉及）
#	建议	来源仓库	优先级
1	跨平台 GPU 后端自动检测（MLX/CUDA/ROCm/DirectML/XPU/CPU 自动选择最优后端）	VoiceBox	P1
2	Docker 容器化优化（TTS_MultiModel 已有 Dockerfile，参考 Piper 的 ONNX 轻量部署）	Piper	P2
3	Windows CUDA 二进制自动下载（参考 VoiceBox 的 cuda.py 服务，自动安装匹配的 CUDA 版本）	VoiceBox	P2
4	ROCm AMD GPU 支持（参考 VoiceBox 的 rocm.py，自动配置 HSA_OVERRIDE_GFX_VERSION）	VoiceBox	P2
5	CPU 兜底方案（所有引擎添加 CPU 推理回退路径，参考 Piper 的多质量分级策略）	Piper, VoiceBox	P1
十六、安全与许可证合规（8 个仓库涉及）
#	建议	来源仓库	优先级
1	依赖隔离（各引擎虚拟环境隔离，解决 PyTorch/transformers 版本冲突）	TTS_MultiModel	P0
2	离线优先策略强化（设置 TRANSFORMERS_OFFLINE=1 + HF_HUB_OFFLINE=1 + MODELSCOPE_OFFLINE=1）	TTS_MultiModel	P0
3	显存预检 + 熔断机制（加载前预检 1.5x 模型大小，占用 > 90% 立即终止推理）	TTS_MultiModel	P0
4	Apache 2.0 许可证优先集成（VoxCPM、Fish Speech、CosyVoice 均可直接商用）	VoxCPM, Fish Speech, CosyVoice	P0
5	AGPL/CC-NC 许可证风险评估（ChatTTS AGPLv3+/CC BY-NC 4.0 非商用许可，需法律评估）	ChatTTS	P1
6	Chatterbox 模型许可确认（代码 MIT，模型专有许可，需确认商用条款）	Chatterbox	P1
7	Edge-TTS LGPLv3 动态链接（需确保动态链接无静态链接传染性）	Edge-TTS	P2
8	水印嵌入用于生成音频溯源（参考 OpenVoice wavmark，不可感知水印保护版权）	OpenVoice	P3
十七、MCP / Agent 集成（2 个仓库涉及）
#	建议	来源仓库	优先级
1	内置 MCP 服务器（参考 VoiceBox FastMCP + Streamable HTTP，暴露 speak/transcribe 工具）	VoiceBox	P2
2	Agent 语音输出 API（任何 MCP 感知的 Agent 可调用 TTS_MultiModel 语音输出）	VoiceBox	P2
3	语音人格系统（本地 LLM 驱动角色扮演，将文本改写为角色口吻后再 TTS）	VoiceBox	P3
十八、LoRA 微调训练管线（5 个仓库涉及）
#	建议	来源仓库	优先级
1	LoRA 训练 WebUI（参考 TTS_MultiModel 已有的 training/ 模块，完善训练参数配置界面）	TTS_MultiModel	P1
2	训练数据管理（JSONL 格式 + HuggingFace Dataset + AudioFeatureProcessingPacker）	VoxCPM	P1
3	训练进度追踪 + 可视化（参考 TTS_MultiModel 的 TrainingTracker，loss 曲线实时显示）	TTS_MultiModel	P1
4	多目标 LoRA（分别对 LM/DiT/投影层应用 LoRA，参考 VoxCPM 的配置化 LoRA）	VoxCPM	P2
5	训练数据增强管线（参考 GPT-SoVITS 的数据预处理流程：降噪/切割/标注/校验）	GPT-SoVITS	P2
许可证合规速查
仓库	License	合规要求
VoxCPM	Apache 2.0	可直接借鉴代码
Fish Speech	Apache 2.0	可直接借鉴代码
CosyVoice	Apache 2.0	可直接借鉴代码，模型需遵守 ModelScope 条款
GPT-SoVITS	MIT	可直接借鉴代码
Chatterbox	MIT (代码) / 专有 (模型)	代码可商用，模型需确认条款
VoiceBox	MIT	可直接借鉴代码
StyleTTS2	MIT	可直接借鉴代码
OpenVoice	MIT	可直接借鉴代码
Piper	Apache 2.0	可直接借鉴代码
Bark	MIT	可直接借鉴代码
Bert-VITS2	MIT	可直接借鉴代码
Real-Time-Voice-Cloning	MIT	可直接借鉴代码
Edge-TTS	LGPLv3	需动态链接
ChatTTS	AGPLv3+ / CC BY-NC 4.0	非商用许可，需法律评估
Coqui-TTS	MPL-2.0	可借鉴设计，修改需开源
Tortoise-TTS	Apache 2.0	可直接借鉴代码
EmotiVoice	MIT	可直接借鉴代码
VALL-E	MIT	可直接借鉴代码
各报告共性警告
警告	来源
AGPL/CC-NC 许可证限制：ChatTTS 不可用于商用场景，需法律评估	ChatTTS
依赖冲突风险：多引擎共存时 PyTorch/transformers/numpy 版本不兼容，必须虚拟环境隔离	所有仓库
显存压力警告：2B-4B 参数模型需要 6-12GB VRAM，必须严格显存预检	VoxCPM, Fish Speech, CosyVoice
采样率差异陷阱：16kHz/22050Hz/24kHz/44100Hz 混用会导致音频质量问题	所有仓库
torch.compile 在 Windows 上受限：Triton 不完全支持 Windows，需 CPU/PyTorch 回退方案	VoxCPM
GPT-SoVITS 依赖冲突：gradio<5 + peft<0.18.0 + torchmetrics<=1.5 约束严格	GPT-SoVITS
Chatterbox 使用 --no-deps 安装：torch==2.6 pin 导致依赖隔离	Chatterbox, VoiceBox
Windows 平台特殊处理：CUDA 二进制下载、进程监控、PyInstaller 打包均需平台适配	VoiceBox
避免重引入已移除的复杂度：TTS_MultiModel 已移除 Gradio，应聚焦 FastAPI 架构	TTS_MultiModel
离线模式必须手动设置环境变量：TRANSFORMERS_OFFLINE=1 + HF_HUB_OFFLINE=1 + MODELSCOPE_OFFLINE=1	TTS_MultiModel
统计总览
维度	数据
覆盖仓库数	18 个
覆盖报告数	19 份（含综合汇总）
建议总章节数	18 章
去重后独立建议项	~150 项
P0（立即实施）	~20 项
P1（短期 1-4 周）	~42 项
P2（中期 1-3 月）	~55 项
P3（长期 3-12 月）	~33 项
Apache 2.0 可商用	8 个仓库
MIT 可商用	8 个仓库
LGPL/AGPL 需评估	2 个仓库
