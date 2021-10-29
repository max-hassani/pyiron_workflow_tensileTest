#!/bin/bash

mamba install -c conda-forge ipykernel jupyter

# execute notebooks
current_dir=$(pwd)
i=0;
for f in $(find . -name "*.ipynb" | sort -n); do
    cd $(dirname $f);
    notebook=$(basename $f);
    papermill ${notebook} ${notebook%.*}-out.${notebook##*.} -k "python3" || i=$((i+1));
    cd $current_dir;
done;

# push error to next level
if [ $i -gt 0 ]; then
    exit 1;
fi;
