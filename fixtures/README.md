# Synthetic fixtures

synthetic.czi contains two scenes, two channels and two Z planes of 5 x 7 uint16
pixels. Each plane is constant: scene * 1000 + channel * 100 + z * 10.
Pixel spacing is X = 0.25 um, Y = 0.5 um, Z = 1 um.

It was generated locally with pylibCZIrw 6.1.0 (no experimental or user data).
The fixture is covered by this repository's MIT license. The test suite reads it
with czifile; pylibCZIrw is not required to use or test the app.


## Public instrument samples

`vendor-samples.json` records upstream URLs, byte lengths and SHA-256 hashes.
Public samples are downloaded to ignored `tools/vendor-fixtures`; their binaries
are not redistributed or relicensed by this repository.

Run `.venv\Scripts\python.exe -X utf8 test_vendor_formats.py --download` once
(about 21 MB). Later runs are offline and verify every fixture hash. Without the
cache, the public suite explicitly skips. The generated suites always run.

- [readlif samples](https://github.com/Arcadia-Science/readlif/tree/master/tests/artifacts):
  Leica XZ and wavelength scans; independently exported Fiji/Bio-Formats TIFF planes.
- [pyABF samples](https://github.com/swharden/pyABF/tree/main/data/abfs):
  multi-channel ABF1 with tags and episodic ABF2.
- [Neo testing data](https://gin.g-node.org/NeuralEnsemble/ephy_testing_data):
  Spike2 SMR, Plexon PLX, Intan RHD and NeuroExplorer NEX recordings.

The public suite compares full exported arrays and parsed metadata, not just file
readability. When development-only `pyabf` is installed, it also independently
checks all ABF sweeps/channels against pyABF within float32 reader precision.
Leica reference TIFF comparisons run without extra development dependencies.
