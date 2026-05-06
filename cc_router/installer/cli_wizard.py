"""
CLI Wizard — 交互式安装向导，菜单选择组件安装。

用法:
    python -m cc_router.installer.cli_wizard
"""

import sys
from pathlib import Path

from .env_detector import detect, print_report
from .config_writer import generate_config, write_config, write_env_script


class Wizard:
    """Interactive installation wizard."""

    def __init__(self):
        self.info = detect()
        self.config = None
        self.selected = {
            "hermes": False,
            "openclaw": False,
            "cc_instances": True,
            "mcp_tools": True,
        }

    def run(self):
        """Run the full wizard flow."""
        self._header()
        print_report(self.info)
        self._menu()

    def _header(self):
        print()
        print("  ╔══════════════════════════════════════════════╗")
        print("  ║        CC Router — 交互式安装向导          ║")
        print("  ║     Universal Multi-Agent ↔ Multi-CC Hub   ║")
        print("  ╚══════════════════════════════════════════════╝")
        print()
        print("  本向导将帮助你在本机安装和配置 CC Router。")
        print("  系统会自动检测环境，然后由你选择安装组件。")
        print()

    def _menu(self):
        """Main menu loop."""
        while True:
            print()
            print("  ────────────────────────────────────────────")
            print("  请选择要配置的组件：")
            print()

            options = [
                ("1", "CC 实例", self._config_cc, self.info.cc_cli.available),
                ("2", "Hermes Adapter", self._config_hermes, self.info.hermes.available),
                ("3", "OpenClaw Adapter", self._config_openclaw, self.info.openclaw.available),
                ("4", "MCP 工具", self._config_mcp, True),
                ("5", "Hub 配置", self._config_hub, True),
                ("6", "生成配置", self._generate, True),
            ]

            for key, label, _, enabled in options:
                print(f"     [{key}] {label}{' (不可用)' if not enabled else ''}")

            print()
            print("     [q] 退出")
            print()

            choice = input("  > 请输入选项: ").strip().lower()

            if choice == "q":
                print("  退出安装向导。")
                break

            for key, _, handler, enabled in options:
                if choice == key and enabled:
                    handler()
                    break

    def _config_cc(self):
        """Configure CC instances."""
        print()
        print("  ── CC 实例配置 ──")
        print()
        print(f"  发现 CC CLI: {self.info.cc_cli.path or '未发现'}")

        if not self.info.cc_cli.available:
            print("  ⚠ 未找到 claude CLI，跳过 CC 实例配置。")
            return

        print()
        from .config_writer import generate_config

        temp_config = generate_config(self.info)
        instances = temp_config.get("cc_instances", [])

        if not instances:
            print("  ⚠ 没有可自动配置的 CC 实例。")
            return

        for i, inst in enumerate(instances):
            print(f"  [{i + 1}] {inst['cc_id']}")
            print(f"      workspace: {inst['workspace']}")
            print(f"      tags: {', '.join(inst['tags'])}")
            print(f"      capabilities: {', '.join(inst['capabilities'])}")
            print()

        self.selected["cc_instances"] = True
        print("  ✓ CC 实例已配置。")

    def _config_hermes(self):
        """Toggle Hermes adapter."""
        print()
        print("  ── Hermes Adapter 配置 ──")
        print()
        print(f"  发现 Hermes: {self.info.hermes.path}")
        print(f"  版本: {self.info.hermes.version}")
        print()

        enable = self._ask_yes_no("  启用 Hermes Adapter？")
        self.selected["hermes"] = enable

        if enable:
            print("  ✓ Hermes Adapter 已启用（子进程模式）。")
            print("    通过 hermes chat -q <task> 调用本地 Hermes Agent")
            print()

            # Test connection
            test = self._ask_yes_no("  是否测试 Hermes 连接？")
            if test:
                self._test_hermes()

    def _config_openclaw(self):
        """Toggle OpenClaw adapter."""
        print()
        print("  ── OpenClaw Adapter 配置 ──")
        print()
        print(f"  发现 OpenClaw: {self.info.openclaw.path}")
        print(f"  版本: {self.info.openclaw.version}")
        print()

        enable = self._ask_yes_no("  启用 OpenClaw Adapter？")
        self.selected["openclaw"] = enable

        if enable:
            print("  ✓ OpenClaw Adapter 已启用（子进程模式）。")
            print("    通过 openclaw agent --local --message 调用本地 OpenClaw")
            print()

            test = self._ask_yes_no("  是否测试 OpenClaw 连接？")
            if test:
                self._test_openclaw()

    def _config_mcp(self):
        """Configure MCP tools."""
        print()
        print("  ── MCP 工具配置 ──")
        print()

        if not self.info.mcp_installed:
            print("  ⚠ mcp 包未安装。")
            install = self._ask_yes_no("  是否安装 mcp 包？")
            if install:
                self._pip_install("mcp")
        else:
            print("  ✓ mcp 包已安装。")

        print()
        print("  可用 MCP 工具：")
        tools = [
            "feishu_notify",
            "forward_to_agent",
            "read_training_log",
            "query_experiment_data",
        ]
        for tool in tools:
            print(f"    • {tool}")
        print()

    def _config_hub(self):
        """Configure Hub settings."""
        print()
        print("  ── Hub 核心配置 ──")
        print()

        port = input("  Hub 端口 (默认 8765): ").strip()
        self._hub_port = int(port) if port.isdigit() else 8765

        timeout = input("  默认超时秒数 (默认 300): ").strip()
        self._hub_timeout = float(timeout) if timeout.replace(".", "").isdigit() else 300.0

        log_levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
        print("  日志级别:")
        for i, level in enumerate(log_levels, 1):
            print(f"    [{i}] {level}")
        lvl = input("  选择日志级别 (默认 2=INFO): ").strip()
        try:
            self._hub_loglevel = log_levels[int(lvl) - 1]
        except (ValueError, IndexError):
            self._hub_loglevel = "INFO"

        print("\n  ✓ Hub 配置:")
        print(f"    端口: {self._hub_port}")
        print(f"    超时: {self._hub_timeout}s")
        print(f"    日志: {self._hub_loglevel}")

    def _generate(self):
        """Generate configuration files."""
        print()
        print("  ── 生成配置文件 ──")
        print()

        # Gather settings
        port = getattr(self, "_hub_port", 8765)
        timeout = getattr(self, "_hub_timeout", 300.0)
        log_level = getattr(self, "_hub_loglevel", "INFO")

        # Generate
        config = generate_config(
            self.info,
            enable_hermes=self.selected["hermes"],
            enable_openclaw=self.selected["openclaw"],
            hub_port=port,
            timeout=timeout,
            log_level=log_level,
        )

        config_path = write_config(config)
        print(f"  ✓ 配置文件: {config_path}")

        env_path = write_env_script(self.info)
        print(f"  ✓ 环境脚本: {env_path}")

        print()
        print("  配置摘要:")
        print("  ────────────────────────────────────────────")
        print(f"  CC 实例:    {len(config.get('cc_instances', []))} 个")
        print(f"  Hermes:     {'✓' if self.selected['hermes'] else '✗'}")
        print(f"  OpenClaw:   {'✓' if self.selected['openclaw'] else '✗'}")
        print(f"  MCP 工具:   {len(config.get('mcp_tools', []))} 个")
        print(f"  Hub 端口:   {port}")
        print("  ────────────────────────────────────────────")
        print()
        print("  启动 Hub:")
        print("    python -m cc_router.installer.cli_wizard start")
        print()

    def _test_hermes(self):
        """Test Hermes CLI connectivity."""
        print("  正在测试 Hermes 连接...")
        import asyncio

        try:
            from cc_router.hermes_executor import HermesExecutor

            async def test():
                exec = HermesExecutor()
                result = await exec.run(task="Just say 'OK'", timeout=30.0)
                if result.kind == "SUCCESS":
                    print(f'  ✓ Hermes 连接成功: "{result.text[:60]}"')
                else:
                    print(f"  ⚠ Hermes 返回: {result.kind}: {result.error[:80]}")

            asyncio.run(test())
        except Exception as e:
            print(f"  ⚠ Hermes 测试失败: {e}")

    def _test_openclaw(self):
        """Test OpenClaw CLI connectivity."""
        print("  正在测试 OpenClaw 连接...")
        import asyncio

        try:
            from cc_router.openclaw_executor import OpenClawExecutor

            async def test():
                exec = OpenClawExecutor()
                result = await exec.run(task="Just say 'OK'", timeout=60.0)
                if result.kind == "SUCCESS":
                    print(f'  ✓ OpenClaw 连接成功: "{result.text[:60]}"')
                else:
                    print(f"  ⚠ OpenClaw 返回: {result.kind}: {result.error[:80]}")

            asyncio.run(test())
        except Exception as e:
            print(f"  ⚠ OpenClaw 测试失败: {e}")

    def _ask_yes_no(self, prompt: str) -> bool:
        """Ask a yes/no question."""
        while True:
            r = input(f"  {prompt} (y/n): ").strip().lower()
            if r in ("y", "yes"):
                return True
            if r in ("n", "no"):
                return False
            print("  请输入 y 或 n。")

    def _pip_install(self, package: str):
        """Install a pip package."""
        import subprocess

        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", package],
                check=True,
                capture_output=True,
                timeout=60,
            )
            print(f"  ✓ {package} 已安装。")
            self.info.mcp_installed = True
        except subprocess.CalledProcessError as e:
            print(f"  ⚠ 安装失败: {e.stderr.decode()[:200]}")

    def start_hub(self):
        """Start the Hub with the generated config."""
        print()
        print("  启动 CC Router Hub...")
        print()
        config_path = Path.cwd() / "cc_router_config.json"
        if not config_path.exists():
            print("  ⚠ 配置文件不存在，请先运行安装向导生成配置。")
            print("    python -m cc_router.installer.cli_wizard")
            return

        import json

        config = json.loads(config_path.read_text())

        import asyncio
        from cc_router.router_hub import get_global_hub
        from cc_router.cc_adapter import CCAdapter

        async def run_hub():
            hub = get_global_hub()

            # Register CC instances
            for inst_cfg in config.get("cc_instances", []):
                cc = CCAdapter(
                    cc_id=inst_cfg["cc_id"],
                    workspace=inst_cfg["workspace"],
                    tags=inst_cfg.get("tags", []),
                    capabilities=inst_cfg.get("capabilities", []),
                    cc_cli_path=inst_cfg.get("cc_cli_path"),
                )
                hub.register_cc(cc)
                print(f"  ✓ CC 实例已注册: {inst_cfg['cc_id']}")

            # Connect Hermes
            if "hermes" in config.get("adapters", {}):
                from cc_router.adapters.hermes_adapter import HermesAgentAdapter

                hermes = HermesAgentAdapter(
                    agent_id=config["adapters"]["hermes"]["agent_id"],
                    hermes_path=config["adapters"]["hermes"]["hermes_path"],
                )
                hub.connect_agent(hermes.agent_id, hermes)
                print("  ✓ Hermes Adapter 已连接")

            # Connect OpenClaw
            if "openclaw" in config.get("adapters", {}):
                from cc_router.adapters.openclaw_adapter import OpenClawAgentAdapter

                openclaw = OpenClawAgentAdapter(
                    agent_id=config["adapters"]["openclaw"]["agent_id"],
                    openclaw_path=config["adapters"]["openclaw"]["openclaw_path"],
                )
                hub.connect_agent(openclaw.agent_id, openclaw)
                print("  ✓ OpenClaw Adapter 已连接")

            print()
            print("  CC Router Hub 已启动")
            print(f"  {'=' * 40}")
            print(f"  CC 实例: {len(config.get('cc_instances', []))}")
            agents = hub.registry.list_all_sync()
            print(f"  已连接 Agent: {len(agents)}")
            print(f"  {'=' * 40}")
            print()
            print("  按 Ctrl+C 停止")

            # Keep running
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\n  正在停止 Hub...")

        asyncio.run(run_hub())


def main():
    """Entry point."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "start":
        Wizard().start_hub()
    else:
        Wizard().run()


if __name__ == "__main__":
    main()
