#!/bin/bash

mamba install -c conda-forge ipykernel jupyter nbconvert

# execute notebooks
current_dir=$(pwd)
i=0;
for f in $(find . -name "*.ipynb" | sort -n); do
    notebook=$(basename $f);
    jupyter nbconvert --ExecutePreprocessor.timeout=9999999 --to notebook --execute $f || i=$((i+1));
    cd $current_dir;
done;

# push error to next level
if [ $i -gt 0 ]; then
    exit 1;
fi;
