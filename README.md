# lxmpicturelab

Compare and experiment with different picture formation algorithms using
various image sources.

![lxmpicturelab-cover.jpg](site/img/lxmpicturelab-cover.jpg)

The results are published to https://mrlixm.github.io/lxmpicturelab.

> ⚠️ This repository is currently partially public, the source image assets
> are not version-controlled yet.

## what

These are the tasks this repository defines:

1. stores photographic and cgi image source assets retrieved from external web
   sources.
    - generate consistent metadata for them
    - uniformize them (size, file format, encoding, ...)
2. combine all those assets to a single "set" image (a mosaic).
3. build a picture formation algorithm to be usable as a "renderer"
4. render the images generated in 2. with one or multiple renderers of 3.
   to generate a set of "comparison" images.
5. run and publish the results to a static website

All those tasks match an executable python script:

1. [asset-in-ingest.py](scripts/asset-in-ingest.py)
2. [sets-generate.py](scripts/sets-generate.py)
3. [renderer-build.py](scripts/renderer-build.py)
4. [comparisons-generate.py](scripts/comparisons-generate.py)
5. [site-build.py](site/site-build.py)

## scripts usage

### pre-requisites

- [uv](https://docs.astral.sh/uv/) for python project management
- [git](https://git-scm.com/downloads) for doc publish / contributing to this
  repo

preparation:

- download this repository anywhere on your system
- `cd path/to/repo`
- `uv sync` : create the python virtual environment

To run a script you can use the following template:

```
uv run script/path/scriptname.py
```

### asset-in-ingest.py

⚠️ This script requires you for now to manually download each image source
from its url listed the json metadata file.

You can then check the README in [assets/](assets) to better understand the
asset workflow.

### sets-generate.py

This scripts requires the assets in [assets/](assets) to exists.

The current configuration will combine all the existing assets found in the
directory.

You can create additional variants by editing the global variable
`SET_VARIANTS` and adding it a new `SetVariant` instance. You can restrict
which assets are combine by setting the `SetVariant.asset_filter` field.

The output of this script is found at [sets/](sets) (currently not
version-controlled).

### renderer-build.py

Use `uv run renderer-build.py --help` to display its documentation.

Will build the necessary resources to use a picture formation algorithm
specified
from online sources (requires internet connection).

### comparisons-generate.py

Use `uv run comparisons-generate.py --help` to display its documentation.

This script depends on:

- the image file generated by previous scripts which are provided
  by giving their asset identifier (manual execution needed).
- the renderers generated by `renderer-build.py` (automatically executed).

By default, the comparison results and the renderers are stored in an
[.workbench/](.workbench) directory at root. You can change those with the
command line interface.

### site-build.py

Creates a static html website with a specific set of assets,
that are run through `comparisons-generate.py`.

The html is manually authored, with the help of Jinja2 templating.

The comparisons results will be stored in a different directory but only need
to be generated once. You can then quickly rebuild the html website without
waiting for the long comparisong process.
