# Synthetic fixtures

synthetic.czi contains two scenes, two channels and two Z planes of 5 x 7 uint16
pixels. Each plane is constant: scene * 1000 + channel * 100 + z * 10.
Pixel spacing is X = 0.25 um, Y = 0.5 um, Z = 1 um.

It was generated locally with pylibCZIrw 6.1.0 (no experimental or user data).
The fixture is covered by this repository's MIT license. The test suite reads it
with czifile; pylibCZIrw is not required to use or test the app.
