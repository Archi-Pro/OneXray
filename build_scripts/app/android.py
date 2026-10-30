import shutil
from pathlib import Path

from app.builder import Builder
from app.command_line import flutter_command, run_command


class AndroidBuilder(Builder):
    def build_app(self):
        run_command(
            [
                flutter_command(),
                "build",
                "appbundle",
                "--target-platform",
                "android-arm,android-arm64,android-x86,android-x64",
            ],
            cwd=self.root_dir,
        )
        fastlane_sa = Path(self.project_dir) / "fastlane/playservice.json"
        if fastlane_sa.exists():
            try:
                run_command(
                    ["fastlane", "deploy", "--verbose"],
                    cwd=self.project_dir,
                    env={"ONEXRAY_BUILD_NUMBER": str(self.build_number)},
                )
            except Exception:
                pass
        run_command(
            [
                flutter_command(),
                "build",
                "apk",
                "--split-per-abi",
            ],
            cwd=self.root_dir,
        )
        apk_dir = Path(self.root_dir) / "build/app/outputs/flutter-apk"
        for apk in apk_dir.glob("app-*-release.apk"):
            abi = apk.stem.replace("app-", "").replace("-release", "")
            dest = Path(self.output_dir) / f"OneXray-android-{abi}.apk"
            shutil.copy2(apk, dest)
        universal_apk = apk_dir / "app-release.apk"
        universal_dest = Path(self.output_dir) / "OneXray-android-universal.apk"
        if universal_apk.exists() and not universal_dest.exists():
            shutil.copy2(universal_apk, universal_dest)
        aab_path = Path(self.root_dir) / "build/app/outputs/bundle/release/app-release.aab"
        if aab_path.exists():
            shutil.copy2(
                aab_path,
                self.output_dir,
            )
