# Mac Local Run Notes

This checkout is configured to use:

```bash
export PROJECT_ROOT="/Users/davidfang/PyCharmMiscProject/minicondapythonProject1/计算机视觉大作业"
export REPO_DIR="$PROJECT_ROOT/badminton-pipeline-repro"
export PYTHON_BIN="/opt/miniconda3/envs/pytorch_env/bin/python"
export ANALYSIS_DIR="$REPO_DIR/output/analysis"
cd "$REPO_DIR"
```

Run the full pipeline:

```bash
PYTHON_BIN="$PYTHON_BIN" ANALYSIS_DIR="output/analysis" scripts_mac/06_run_full_pipeline.sh
```

Run stages manually:

```bash
$PYTHON_BIN scripts_mac/00_check_env.py | tee output/analysis/logs/00_check_env.log
scripts_mac/01_install_deps.sh
scripts_mac/02_fetch_assets.sh
scripts_mac/03_run_analysis.sh
$PYTHON_BIN scripts_mac/04_validate_outputs.py | tee output/analysis/logs/04_validate_outputs.log
$PYTHON_BIN scripts_mac/05_export_json.py | tee output/analysis/logs/05_export_json.log
```

Expected outputs:

```text
output/analysis/short_ball.csv
output/analysis/end1_fix_swap2_precision_full_regen.mp4
output/analysis/end1_fix_swap2_precision_full_fx_regen.mp4
output/analysis/motionstats_summary.json
output/analysis/analysis_summary.json
output/analysis/result.json
output/analysis/logs/
```
