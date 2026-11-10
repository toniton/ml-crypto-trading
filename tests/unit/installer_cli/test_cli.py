from installer.cli import (
    apply_profile_defaults,
    build_pipeline,
    create_argument_parser,
    main,
)
from installer.context import InstallProfile, InstallerContext


def test_argument_parser_default_profile():
    parser = create_argument_parser()
    args = parser.parse_args([])
    assert args.profile == InstallProfile.QUICKSTART.value


def test_argument_parser_non_interactive_flag():
    parser = create_argument_parser()
    args = parser.parse_args(["--non-interactive"])
    assert args.non_interactive is True


def test_argument_parser_dry_run_flag():
    parser = create_argument_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_build_pipeline_includes_dependencies_by_default():
    steps = build_pipeline(skip_deps=False)
    step_names = [s.name for s in steps]
    assert "Python Environment & Dependencies Setup" in step_names


def test_build_pipeline_excludes_dependencies_when_skipped():
    steps = build_pipeline(skip_deps=True)
    step_names = [s.name for s in steps]
    assert "Python Environment & Dependencies Setup" not in step_names


def test_cli_main_dry_run_non_interactive_returns_success():
    exit_code = main(["--non-interactive", "--dry-run", "--skip-deps", "--skip-db", "--skip-migrations"])
    assert exit_code == 0


def test_apply_profile_defaults_developer_enables_dev_deps(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv", profile=InstallProfile.DEVELOPER)
    apply_profile_defaults(context)
    assert context.install_dev_deps is True


def test_apply_profile_defaults_developer_sets_staging_env(tmp_path):
    context = InstallerContext(project_root=tmp_path, venv_dir=tmp_path / "venv", profile=InstallProfile.DEVELOPER)
    apply_profile_defaults(context)
    assert context.app.app_env == "staging"
