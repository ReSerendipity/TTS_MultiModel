# 发布/回滚/SLA 总纲（Release Governance）

> **本仓为家族发布/回滚/SLA 关键源仓之一**：`docs/SRE_RUNBOOK.md`（SLA/SLO/回滚/DR 演练）与 `docs/rollback_sop.md`（一键回滚 SOP + `scripts/rollback_release.py`）即为权威实体版。
> **来源**：家族通用 `.spec_audit/family_release_governance.md`（泛化自本仓 + DraftPeek VERSIONING.md），此处为总览索引。
> **适用范围**：TTS_MultiModel 全项目发布、回滚与运行稳定性。

---

## 1. 版本号规范

- 遵循 SemVer `MAJOR.MINOR.PATCH`。**源码版本 2.2.2（未发布）｜已发布最新 = v2.2.1**。
  版本号出现在 11 处（`version.json`/`pyproject.toml`/`config.yaml`/`desktop/*`/`scripts/installer/setup.nsi`），
  但只有 tag + GitHub Release 同时存在才算发出去；核对：`gh release view v<版本>`。
- 版本位：`pyproject.toml` + `config.yaml`（release-please 驱动前端缓存参数需人工补齐，见本地 AGENTS.md #9（AGENTS.md 为本地维护、不随仓库分发））+ `CHANGELOG.md`。
- 发布由 `release-please` 自动生成 GitHub Release 并打 semver tag；该作业若失败**不会**再被吞掉
  （v2.2.2 曾在工作流全绿的情况下既没 tag 迁移也没 Release，原因见 `CHANGELOG.md` 该条标注）。

### 1.1 存量依赖债务卡：便携钉版 `transformers` 低于自家下界

| 项 | 值 |
|---|---|
| 违规 | `requirements-lock.txt` 与 `launcher/requirements-small.txt` 钉 `transformers==4.52.1` |
| 下界 | `pyproject.toml:59` + `requirements.txt:5` 均声明 `>=4.57.0`，理由写在 pyproject：VoxCPM2 / IndexTTS2 的 tokenizer 与 modeling 需要较新 transformers API |
| 连带 | `transformers 4.57.0` 的元数据要求 **`tokenizers>=0.22.0,<=0.23.0`**（PyPI 实测），而我们钉 `tokenizers==0.21.0` → **不是单包 bump，必然连带 tokenizers** |
| 未受阻项 | `huggingface-hub==0.36.2`（需 `>=0.34,<1.0` ✔）、`numpy==2.5.2` ✔、`safetensors==0.8.0` ✔、`pydantic==2.13.4` ✔；`requirements.txt:6` 只声明 `tokenizers>=0.19.0`，无上游 vendor 钉死 0.21.0 |
| 为什么当初降到 4.52.1 | 见 `CHANGELOG.md`「便携钉装自洽修复」：全新 WinPython 3.12.10.1 上 `pip install -r requirements-small.txt` 报 `ResolutionImpossible`，当时按 `.venv` 实测值对齐了 9 项 |

修它的正确顺序（属发布级动作，需真机；不要只改两行就发）：

```bash
# 1) 全量解析验证（先只解析不装）：把两文件里的 transformers/tokenizers 改为
#    transformers==4.57.* 与 tokenizers==0.23.* 后
python -m pip install --dry-run --ignore-installed --report /tmp/res.json \
    -r launcher/requirements-small.txt
# 2) 解析通过再重建便携包并过门禁（需要 ≥60GB 磁盘的 self-hosted runner）
pwsh scripts/build_portable_bundle.ps1 ... ; pwsh scripts/release_gate.ps1 -Mode real
# 3) 门禁绿了以后，把 CI 白名单收紧 —— 见 security.yml 的 --allow-debt
python scripts/check_pin_floors.py            # 不带 --allow-debt，应为 0 违规
```

当前 `python scripts/check_pin_floors.py` 实测：25 个声明下界 / 93 个钉版 / **1 处违规**。
CI 侧（`Security Scan` 的 pip-audit job）用 `--allow-debt transformers` 棘轮化：
存量只报不拦，名单外新增即红；**这条债务修好后必须把 `transformers` 从白名单删掉**。

## 2. 发布流程

0. **main 不可直推**：分支保护要求 3 项状态检查且 `enforce_admins=true`，
   直推会被 `GH006: 3 of 3 required status checks are expected` 拒绝（admin 也一样）。
   一切变更走 PR；下面第 2 步的「push 触发」实际发生在 PR 合入那一刻。
0.5 发布前置断言：`python scripts/check_pin_floors.py --allow-debt transformers` 必须 0 违规，
   且**白名单应逐次清空**。当前存量债务是便携钉版 `transformers==4.52.1` 低于
   `pyproject.toml:59` 声明的 `>=4.57.0`（理由：VoxCPM2/IndexTTS2 的 tokenizer 与 modeling
   需要较新 transformers API）——修它要重做便携包依赖解析并在真机验证，属发布级动作。
1. 确认 CHANGELOG `[Unreleased]` 条目完整；release-please 提交后自动收敛版本
2. PR 合入 main 触发 `release-please.yml`
3. 同步 `config.yaml` 顶层 `version`（release-please 不自动同步，需人工）
4. CI 盯到终态；容器镜像钉 digest 发布，禁止 `:latest`

## 3. 回滚（详见 `docs/rollback_sop.md`）

- 判定：成功率跌破 SLO / readiness degraded / P0-P1 安全 / 契约断裂。
- 执行：`python scripts/rollback_release.py --target v<tag>`（反向 revert，保历史）+ 切镜像 tag / `kubectl rollout undo`。
- 权重/DB：权重为外部挂载与回滚无关；SQLite 不随代码回滚（有迁移兼容）。

## 4. SLA / 错误预算（详见 `docs/SRE_RUNBOOK.md` §1）

- 可用性 ≥99.5%（月度）⇒ 错误预算 ≈ 3.6h/月。
- liveness `/api/health/ping`（内存级）；readiness `/api/health/ready` / `/readyz`（深度）。

## 5. 发布前检查清单

- [ ] 版本位全部同步（`pyproject.toml` + `config.yaml` + `CHANGELOG.md`）
- [ ] CHANGELOG `[Unreleased]` 已改版本 + 日期
- [ ] 全量 pytest 通过（门禁实测：非 GPU 回归 0 failed）
- [ ] `ruff` 全绿；mypy 遵守 `.ci/mypy_baseline.txt` 棘轮
- [ ] `python scripts/check_spec_refs.py` 退出码 0
- [ ] 镜像 digest 钉版 + Trivy 关键/高危扫描绿
- [ ] 完整性自检 16/16 通过
- [ ] tag 已推送触发 `release-please.yml`