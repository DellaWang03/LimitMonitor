import hashlib
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.paths import PipelinePaths
from src.testing.current_issuer_resolver import (
    CurrentIssuerResolverError,
    stage_current_issuer_resolver,
    validate_current_issuer_resolver,
)


def _write_sources(tmp_path: Path) -> tuple[Path, Path]:
    mapping = tmp_path / "issuer_wind_code_mapping.csv"
    mapping.write_text(
        "发行人,wind代码\n甲公司,1001\n乙公司,1002\n",
        encoding="utf-8-sig",
    )
    zero_source = tmp_path / "风控部债券池_主体.xlsx"
    pd.DataFrame(
        {
            "日期": ["2026-07-13", "2026-07-13", "2026-07-13"],
            "发行人名称": ["无代码甲", "无代码乙", "有代码丙"],
            "主体池": ["C", "C", "A"],
            "发行人wind代码": ["0.0", 0, "3003"],
        }
    ).to_excel(zero_source, index=False)
    return mapping, zero_source


def test_validate_current_sources_records_hashes_and_only_explicit_zeros(
    tmp_path: Path,
) -> None:
    mapping, zero_source = _write_sources(tmp_path)

    validated = validate_current_issuer_resolver(mapping, zero_source)

    assert validated.mapping_file == mapping.resolve()
    assert validated.zero_result_source == zero_source.resolve()
    assert validated.mapping_sha256 == hashlib.sha256(mapping.read_bytes()).hexdigest()
    assert validated.zero_result_source_sha256 == hashlib.sha256(
        zero_source.read_bytes()
    ).hexdigest()
    assert validated.mapping_row_count == 2
    assert validated.zero_results == (("无代码甲", "0"), ("无代码乙", "0"))


def test_validate_current_sources_rejects_conflicting_mapping(tmp_path: Path) -> None:
    mapping, zero_source = _write_sources(tmp_path)
    mapping.write_text(
        "发行人,wind代码\n甲公司,1001\n甲公司,9999\n",
        encoding="utf-8-sig",
    )

    with pytest.raises(CurrentIssuerResolverError, match="重复"):
        validate_current_issuer_resolver(mapping, zero_source)


def test_validate_current_sources_rejects_symlink(tmp_path: Path) -> None:
    mapping, zero_source = _write_sources(tmp_path)
    outside = tmp_path / "outside.csv"
    outside.write_bytes(mapping.read_bytes())
    mapping.unlink()
    mapping.symlink_to(outside)

    with pytest.raises(CurrentIssuerResolverError, match="符号链接"):
        validate_current_issuer_resolver(mapping, zero_source)


def test_stage_current_sources_uses_only_isolated_fixed_paths(tmp_path: Path) -> None:
    mapping, zero_source = _write_sources(tmp_path)
    validated = validate_current_issuer_resolver(mapping, zero_source)
    before = (mapping.read_bytes(), zero_source.read_bytes())
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    paths = PipelinePaths.create(run_root)

    staged = stage_current_issuer_resolver(validated, paths)

    assert staged.mapping_file == paths.stage0 / "issuer_wind_code_mapping.csv"
    assert staged.result_file == paths.tmp / "temp/wind_codes_result.xlsx"
    assert staged.mapping_file.read_bytes() == mapping.read_bytes()
    result = pd.read_excel(staged.result_file, dtype=str).fillna("")
    assert result.to_dict("records") == [
        {"发行人名称": "无代码甲", "Wind代码": "0"},
        {"发行人名称": "无代码乙", "Wind代码": "0"},
    ]
    assert before == (mapping.read_bytes(), zero_source.read_bytes())


def test_stage_current_sources_refuses_existing_target(tmp_path: Path) -> None:
    mapping, zero_source = _write_sources(tmp_path)
    validated = validate_current_issuer_resolver(mapping, zero_source)
    run_root = tmp_path / "run"
    run_root.mkdir(mode=0o700)
    paths = PipelinePaths.create(run_root)
    (paths.stage0 / "issuer_wind_code_mapping.csv").write_text(
        "pre-existing", encoding="utf-8"
    )

    with pytest.raises(CurrentIssuerResolverError, match="已存在"):
        stage_current_issuer_resolver(validated, paths)
