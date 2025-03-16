# assets

Each "asset" is a single test image with its associated metadata.

## conventions

Any other data not mentioned here imply being arbitrary and not guaranteed to
be stable or similar across files.

### filesystem structure

- Each single image MUST have a side-car json metadata.
- The side-car json MUST have the same name as the file.
- Directories ARE NOT allowed.
- Each file MAY HAVE a single thumbnail.

### file names

File name are specified as 3 dash-separated tokens:

```
{pseudoReference}-{randomId}-{contentApproximation}
```

where:

- `{pseudoReference}`: 6 char max, build from the source and author of the content.
  First letter MUST be a `P` for Plates and `C` for Cgi
- `{randomId}`: random string of 3 uppercase alphanumeric characters
- `{contentApproximation}`: a single word of 12 character max that roughly
  characterize the subject of the content. Only alphanumeric characters

file names are not intented to hold any specific information other than providing
a human-familiar unique identifier for assets.

### side-car json

- the file MUST follow the standard json syntax
- the file MUST have the following keys:
    - `source` (str): an url or a file name
    - `authors` (list of str): list of image authors/owners
    - `references` (list of str): list of urls mentioning the image
    - `capture-gamut` (str): gamut in which the original image was captured
    - `primary-color` (str): the main visible color on this image
    - `type` (str): `cgi` or `plate`
- the file MAY have the following keys:
    - `context` (str): arbitrary description of the image content
    - `license` (str): a partial or full license IF specified by the author
- the file MAY have other keys

### image encoding

- image MUST be a valid OpenEXR file
- image MAY have different bitdepth and compressions
  - _plates_ are usually `16bit half-float`, _cgi_ is usually `32bit float`
  - compression is usually `zip`
- image MUST be `ACES2065-1` encoded
- image SHOULD be under `2202` pixel of width

> [!NOTE]
> The ACES2065-1 encoding is a convenience. Because currently you have more
> chance to find an ACES2065-1 colorspace in any DCC to interpret the file
> than more sensisble alternative like BT.2020 or CIE-XYZ.

## developer workflow

All pre-assets are first put in an `.assets-in` directory at the root
of the repository:

```shell
repo-root/
  .assets-in/
    Ceg-TR4-demo.tif
    Ceg-TR4-demo.json
    ...
  assets/
    ...
    README.md
  scripts/
    ...
```

This directory has for purpose to store the pre-assets before their ingestion.
In some case they might be in the same state we retrived them from their author,
in some other case we need to perform an additional manual 
pre-ingestion-processing step to conform them if they are not compatible 
with the ingestion script.

When we talk about ingestion we mean running the `.assets-in` directory content
through the [asset-in-ingest.py](../scripts/asset-in-ingest.py) script.
This script use OIIOTOOL which doesn't support all image formats. 
For example a camera RAW format will need a _pre-ingestion-processing_ step.

### pre-ingestion-processing

image-processing workflow for assets that are not compatible with the ingestion
script and need a pre-processing step:

- processed through Nuke 15.0v4
- all rescaling operation done with a `cubic` filter
- colorspace processing done with the ACES OCIO config variant `studio` v2.0.0

