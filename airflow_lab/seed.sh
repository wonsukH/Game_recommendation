#!/usr/bin/env bash
# Seed the scratch dirs with the inputs the pipeline reads but never produces.
# Run from the repo root:  bash airflow_lab/seed.sh
#
# work/ is gitignored, so a fresh clone starts empty and needs this once.
# Everything copied here is an INPUT; all outputs are produced by the DAG.
set -u

cd "$(dirname "$0")/.." || exit 1
W=airflow_lab/work

mkdir -p "$W/outputs/p6" "$W/serving_data" "$W/p6_ood"

copy() {
  if [ -f "$1" ]; then
    cp "$1" "$2" && echo "  ok    $1"
  else
    echo "  MISS  $1" && MISSING=1
  fi
}

MISSING=0
echo "seeding $W"
copy outputs/tag_vocab.json            "$W/outputs/"
copy outputs/p6/pop_unbiased.json      "$W/outputs/p6/"
copy serving/data/tag_vocab.json       "$W/serving_data/"
copy experiments/p6_ood/p6_panels.json "$W/p6_ood/"

if [ "$MISSING" -ne 0 ]; then
  echo
  echo "Some inputs are missing on this machine."
  echo "  outputs/p6/pop_unbiased.json      -> build_catalog_db fails"
  echo "  experiments/p6_ood/p6_panels.json -> p5_validate fails"
  echo "Both are local-only (gitignored). Copy them from the machine that has them."
  exit 1
fi

echo "done"
