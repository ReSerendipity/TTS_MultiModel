"""CSRF 密钥持久化失败时的启动契约。

背景：`app_server.create_app()` 过去在 `data/.csrf_secret` 写不出来时只
`logger.warning` 后用**空密钥**继续挂 `CSRFMiddleware`（注释自称「回退到无签名
模式」）—— 一次磁盘或权限故障就让 CSRF 防护静默自我关闭。现改为默认硬失败，
只读部署需显式设 `TTS_ALLOW_EPHEMERAL_CSRF=1` 才接受内存态密钥。

这里用不存在的盘符制造一次真实的 OS 级失败，而不是 mock 到假。
"""

import pytest
from app.integrated_app import app_server


@pytest.fixture
def bad_project_root(monkeypatch, tmp_path):
    """把工程根指向不存在的盘符：makedirs/open 必然抛 OSError。"""
    missing = "Z:/tts_no_such_drive"
    monkeypatch.setattr(app_server, "_PROJECT_ROOT", missing)
    return missing


class TestCsrfSecretHardFail:
    def test_create_app_refuses_to_start_unsigned(self, bad_project_root):
        with pytest.raises(RuntimeError) as exc:
            app_server.create_app()
        msg = str(exc.value)
        assert "CSRF" in msg, f"抛错来源不是 CSRF 密钥: {msg[:120]}"
        # 报错必须自带可操作出路，而不是只丢一个栈
        assert "可写" in msg and "TTS_ALLOW_EPHEMERAL_CSRF" in msg

    def test_ephemeral_opt_in_clears_the_hard_fail(self, bad_project_root, monkeypatch):
        """显式声明后，CSRF 这条不再拦启动。

        create_app 在 CSRF 之后还会继续访问工程根，所以拿到的可能是别的
        Z: 盘错误 —— 那恰好证明已经走过了 CSRF 这道门。断言只针对
        「逃逸出来的不是 CSRF 硬失败」，不假装后续都成立。
        """
        monkeypatch.setenv("TTS_ALLOW_EPHEMERAL_CSRF", "1")
        escaped: BaseException | None = None
        try:
            app_server.create_app()
        except BaseException as exc:  # noqa: BLE001 - 后续失败与 CSRF 无关，见 docstring
            escaped = exc

        assert not (isinstance(escaped, RuntimeError) and "CSRF" in str(escaped)), (
            f"白名单开关没生效：{str(escaped)[:120]}"
        )
