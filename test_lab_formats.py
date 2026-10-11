"""Generated calibrated lab fixtures, image stacks, genomics and PDF-to-LaTeX checks."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
import struct
import tempfile
import threading
import uuid
import xml.etree.ElementTree as ET

import h5py
import numpy as np
import pymupdf
import tifffile
import any2any as a
import imaging_formats as imaging
import lab_signals as lab


def make_abf(path):
    data = bytearray(8192)
    fields = [(0, '4s', b'ABF '), (4, 'f', 1.3), (8, 'h', 5), (10, 'i', 400), (16, 'i', 2),
              (40, 'i', 12), (92, 'i', 15), (96, 'i', 2), (100, 'h', 0), (120, 'h', 1),
              (122, 'f', 1000), (138, 'i', 200), (244, 'f', 10), (252, 'i', 32768)]
    for offset, fmt, value in fields:
        struct.pack_into('<' + fmt, data, offset, value)
    struct.pack_into('<16h', data, 410, 0, *([-1] * 15))
    data[442:452], data[602:610] = b'Channel 1 ', b'mV      '
    for offset in (730, 922, 1050):
        struct.pack_into('<f', data, offset, 1)
    values = (np.sin(np.arange(400) / 20) * 1000).astype('<i2')
    data[6144:6944] = values.tobytes()
    struct.pack_into('<iiii', data, 7680, 0, 200, 200, 200)
    path.write_bytes(data)
    return values.astype(float) * 10 / 32768


def make_dng(path):
    pixels = (np.arange(64 * 64).reshape(64, 64) % 4096).astype('uint16')
    tags = [(50706, 'B', 4, (1, 4, 0, 0), False), (50707, 'B', 4, (1, 1, 0, 0), False),
            (50708, 's', 0, 'Any2Any synthetic DNG', False), (33421, 'H', 2, (2, 2), False),
            (33422, 'B', 4, (0, 1, 1, 2), False), (50717, 'I', 1, 4095, False),
            (50721, '2i', 9, (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1), False),
            (50778, 'H', 1, 21, False)]
    tifffile.imwrite(path, pixels, photometric=32803, extratags=tags, metadata=None)


def make_bam(path):
    from bamnostic.bgzf import BgzfWriter
    header = b'@HD\tVN:1.6\n@SQ\tSN:chr1\tLN:1000\n'
    seq = b'\x12\x48'  # ACGT, two bases per byte.
    name = b'read1\0'
    cigar = struct.pack('<I', 4 << 4)
    aux = b'NMi' + struct.pack('<i', 2) + b'XCB' + b'C' + struct.pack('<I', 3) + bytes([1, 2, 255]) + b'MDZ4\0'
    core = struct.pack('<iiIIiiii', 0, 10, (60 << 8) | len(name), 1, 4, -1, -1, 0)
    record = core + name + cigar + seq + bytes([30, 31, 32, 33]) + aux
    with BgzfWriter(str(path), 'wb') as stream:
        stream.write(b'BAM\x01' + struct.pack('<i', len(header)) + header + struct.pack('<i', 1))
        stream.write(struct.pack('<i', 5) + b'chr1\0' + struct.pack('<i', 1000))
        stream.write(struct.pack('<i', len(record)) + record)


def main():
    checks = 0
    with tempfile.TemporaryDirectory(prefix='any2any-lab-') as name:
        root, out = Path(name), Path(name) / 'out'
        def convert(source, ext):
            nonlocal checks
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            result = a.convert(source, ext, out)
            assert result and all(file.is_file() and file.stat().st_size and file.parent == out for file in result)
            assert all(file.is_file() for file in out.iterdir())
            assert hashlib.sha256(source.read_bytes()).hexdigest() == before
            checks += 1
            print(f'PASS lab {source.suffix} -> {ext}', flush=True)
            return result

        video = root / 'camera.mov'
        a.run_command([a.imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                       '-i', 'testsrc=size=48x32:rate=5:duration=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)])
        for ext in ('png', 'jpg', 'tiff'):
            assert len(convert(video, ext)) == 5

        camera = root / 'camera.dng'
        make_dng(camera)
        import rawpy
        with rawpy.imread(str(camera)) as raw:
            expected_rgb = raw.postprocess(use_camera_wb=True, output_bps=16)
        for ext in imaging.EXPORTS:
            result = convert(camera, ext)
            if ext == 'tiff':
                assert np.array_equal(tifffile.imread(result[0]), expected_rgb)
            elif ext == 'png':
                import imagecodecs
                assert np.array_equal(imagecodecs.png_decode(result[0].read_bytes()), expected_rgb)

        stack = root / 'stack.ome.tiff'
        values = (np.arange(2 * 3 * 2 * 5 * 7).reshape(2, 3, 2, 5, 7) * 83).astype('uint16')
        tifffile.imwrite(stack, values, ome=True, photometric='minisblack', metadata={'axes': 'TCZYX', 'PhysicalSizeX': .25, 'PhysicalSizeXUnit': 'um'})
        for ext in imaging.EXPORTS:
            result = convert(stack, ext)
            if ext == 'tiff':
                with tifffile.TiffFile(result[0]) as restored:
                    assert restored.series[0].axes == 'TCZYX'
                    assert np.array_equal(restored.asarray(), values)
            elif ext == 'png':
                assert len(result) == 12
                for file, plane in zip(result, values.reshape(12, 5, 7)):
                    assert np.array_equal(imagecodecs.png_decode(file.read_bytes()), plane)
            elif ext == 'npy':
                assert np.array_equal(np.load(result[0], allow_pickle=False), values)
            elif ext == 'h5':
                with h5py.File(result[0]) as restored:
                    assert np.array_equal(restored['image'][()], values)
                    assert restored['image'].attrs['axes'] == 'TCZYX'

        czi = Path(__file__).parent / 'fixtures/synthetic.czi'
        for ext in imaging.EXPORTS:
            result = convert(czi, ext)
            if ext == 'h5':
                assert len(result) == 2
                for index, file in enumerate(result):
                    with h5py.File(file) as restored:
                        assert restored['image'].shape == (2, 2, 5, 7)
                        assert restored['image'][1, 1, 0, 0] == index * 1000 + 110
                        info = json.loads(restored['image'].attrs['metadata_json'])
                        assert info['coord_scales']['X'] == .25e-6
            elif ext == 'png':
                assert len(result) == 8

        import mrcfile
        volume = root / 'volume.mrc'
        voxels = np.linspace(-2, 6, 60, dtype='float32').reshape(3, 4, 5)
        with mrcfile.new(volume) as output:
            output.set_data(voxels)
            output.voxel_size = (2., 3., 4.)
        for ext in ('tiff', 'png', 'h5', 'npz'):
            result = convert(volume, ext)
            if ext == 'tiff':
                assert np.array_equal(tifffile.imread(result[0]), voxels)
            elif ext == 'npz':
                with np.load(result[0], allow_pickle=False) as restored:
                    assert np.array_equal(restored['image'], voxels)
                    assert json.loads(str(restored['metadata_json']))['voxel_size_angstrom'] == [2., 3., 4.]

        imaris = root / 'cells.ims'
        with h5py.File(imaris, 'w') as output:
            for t in range(2):
                for c in range(2):
                    output.create_dataset(f'DataSet/ResolutionLevel 0/TimePoint {t}/Channel {c}/Data', data=np.full((2, 3, 4), 100*t+c, dtype='uint16'))
        result = convert(imaris, 'h5')[0]
        with h5py.File(result) as restored:
            assert restored['image'].shape == (2, 2, 2, 3, 4)
            assert restored['image'][1, 1, 0, 0, 0] == 101

        from Bio import SeqIO
        from Bio.Seq import Seq
        from Bio.SeqRecord import SeqRecord
        from Bio.SeqFeature import SeqFeature, SimpleLocation
        import plasmid_maps
        protein = SeqRecord(Seq('MKL'), id='protein', annotations={'molecule_type': 'protein'})
        protein.features = [SeqFeature(SimpleLocation(0, 2), type='domain')]
        rendered = plasmid_maps.svg(protein)
        assert '3 aa / linear' in rendered and 'marker-end=' not in rendered

        plasmid = root / 'plasmid.dna'
        def packet(kind, content):
            return struct.pack('>BI', kind, len(content)) + content
        sequence = b'ACGT' * 100
        features = b'<Features><Feature name="marker" type="CDS" directionality="2"><Segment range="351-50"/><Q name="label"><V text="marker &amp; tag"/></Q></Feature></Features>'
        plasmid.write_bytes(packet(9, struct.pack('>8sHHH', b'SnapGene', 1, 1, 1)) + packet(0, b'\x01' + sequence) + packet(10, features))
        record = SeqIO.read(plasmid, 'snapgene')
        for ext in ('gb', 'embl', 'fasta', 'xdna', 'svg', 'png', 'pdf'):
            result = convert(plasmid, ext)[0]
            if ext == 'gb':
                restored = SeqIO.read(result, 'genbank')
                assert restored.annotations['topology'] == 'circular'
                assert str(restored.features[0].location) == str(record.features[0].location)
            elif ext == 'svg':
                ET.parse(result)
                assert 'marker &amp; tag' in result.read_text(encoding='utf-8')
        zipped = root / 'reads.fastq.gz'
        with gzip.open(zipped, 'wt', encoding='ascii') as output:
            output.write('@read1\nACGT\n+\nIJKL\n')
        for ext in ('fastq', 'fasta', 'gb'):
            result = convert(zipped, ext)[0]
            assert not result.name.startswith('reads.fastq.')
            if ext == 'fastq':
                assert SeqIO.read(result, 'fastq').letter_annotations['phred_quality'] == [40, 41, 42, 43]

        bam = root / 'alignment.bam'
        make_bam(bam)
        for ext in ('sam', 'fasta', 'fastq', 'csv', 'tsv', 'jsonl'):
            result = convert(bam, ext)[0]
            if ext == 'sam':
                text = result.read_text(encoding='utf-8')
                assert 'NM:i:2' in text and 'XC:B:C,1,2,255' in text and 'MD:Z:4' in text
            if ext == 'fastq':
                rec = SeqIO.read(result, 'fastq')
                assert str(rec.seq) == 'ACGT' and rec.letter_annotations['phred_quality'] == [30, 31, 32, 33]
        sam = root / 'reverse.sam'
        sam.write_text('@HD\tVN:1.6\nread1\t16\tchr1\t1\t60\t4M\t*\t0\t0\tAAGC\tIJKL\n', encoding='utf-8')
        rec = SeqIO.read(convert(sam, 'fastq')[0], 'fastq')
        assert str(rec.seq) == 'GCTT' and rec.letter_annotations['phred_quality'] == [43, 42, 41, 40]
        for suffix, payload in {
            'vcf': '##fileformat=VCFv4.3\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tsample1\nchr1\t001\trs1\tA\tC\t.\tPASS\tDP=12\tGT\t0/1\n',
            'gff3': '##gff-version 3\nchr1\ttest\tgene\t1\t20\t.\t+\t.\tID=gene1;Name=A\n',
            'gtf': 'chr1\ttest\tgene\t1\t20\t.\t-\t.\tgene_id "gene1";\n',
            'bed': 'chr1\t0\t20\tfeature\t10\t+\n',
            'bedgraph': 'chr1\t0\t20\t2.25\n'}.items():
            file = root / f'genome.{suffix}'
            file.write_text(payload, encoding='utf-8')
            for ext in ('csv', 'tsv', 'jsonl'):
                result = convert(file, ext)[0]
                if suffix == 'vcf' and ext == 'jsonl':
                    row = json.loads(result.read_text(encoding='utf-8'))
                    assert row['POS'] == '001' and row['sample1'] == '0/1'

        fast5 = root / 'signal.fast5'
        adc = np.array([10, -5, 200, 1000], dtype='int16')
        with h5py.File(fast5, 'w') as output:
            raw = output.create_group('read_1/Raw')
            import vbz_h5py_plugin
            raw.create_dataset('Signal', data=adc, compression=32020, compression_opts=(0, 2, 1, 1))
            raw.attrs['read_id'], raw.attrs['start_time'] = b'read1', 20
            channel = output.create_group('read_1/channel_id')
            for key, value in dict(sampling_rate=4000., offset=5., range=1500., digitisation=8192., channel_number=b'12').items():
                channel.attrs[key] = value
        for ext in ('h5', 'npz', 'csv'):
            result = convert(fast5, ext)
            if ext == 'npz':
                with np.load(result[0], allow_pickle=False) as restored:
                    assert np.array_equal(restored['signal'], adc)
                    info = json.loads(str(restored['metadata_json']))
                    assert info['sample_rate_hz'] == 4000. and info['calibration_scale_pA'] == 1500/8192

        import pod5
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        run = pod5.RunInfo('run', now, 8191, -8192, {}, 'test', 'flowcell', 'test', 'test', 'run', now, 'sample', 4000, 'test', 'test', 'test', 'test', 'test', 'test', {})
        read = pod5.Read(uuid.uuid4(), pod5.Pore(1, 1, 'test'), pod5.Calibration(5., .125), 1, 20, 100.,
                         pod5.EndReason(pod5.EndReasonEnum.UNKNOWN, False), run, signal=adc)
        pod = root / 'signal.pod5'
        with pod5.Writer(pod) as writer:
            writer.add_read(read)
        for ext in ('h5', 'npz', 'csv'):
            result = convert(pod, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    assert np.array_equal(restored['read_000001'][()], adc)

        abf = root / 'recording.abf'
        expected = make_abf(abf)
        for ext in lab.EXPORTS:
            result = convert(abf, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    keys = [key for key in restored if "_analog_" in key]
                    assert len(keys) == 2
                    assert np.allclose(restored[keys[0]][:, 0], expected[:200], atol=1e-7)
                    meta = json.loads(restored[keys[0]].attrs['metadata_json'])
                    assert meta['sampling_rate_hz'] == 1000. and 'mV' in meta['units']
            elif ext == 'csv':
                result = [file for file in result if '_analog_' in file.name]
                assert len(result) == 2
                with result[0].open(newline='', encoding='utf-8') as stream:
                    rows = list(csv.reader(stream))
                    assert rows[0][0] == 'time_s' and float(rows[2][0]) == .001

        import pyedflib
        from pyedflib import highlevel
        edf = root / 'brain.edf'
        channels = [np.sin(np.arange(200)/10)*20, np.cos(np.arange(100)/10)*10]
        headers = [highlevel.make_signal_header('EEG Fp1', sample_frequency=100), highlevel.make_signal_header('LFP', sample_frequency=50)]
        header = highlevel.make_header(startdate=now.replace(tzinfo=None))
        header['annotations'] = [[.5, .1, 'stimulus']]
        highlevel.write_edf(str(edf), channels, headers, header=header)
        for ext in lab.EXPORTS + ['edf', 'bdf']:
            result = convert(edf, ext)
            if ext == 'npz':
                with np.load(result[0], allow_pickle=False) as restored:
                    info = json.loads(str(restored['metadata_json']))
                    assert info['channel_0000']['sampling_rate_hz'] == 100.
                    assert info['channel_0001']['sampling_rate_hz'] == 50.
                    assert restored['channel_0000'].shape == (200, 1) and restored['channel_0001'].shape == (100, 1)
                    assert info['events']['labels'] == ['stimulus']

        import mne
        fif = root / 'test_raw.fif'
        raw = mne.io.RawArray(np.array([channels[0], channels[0]*2])*1e-6, mne.create_info(['EEG1', 'EEG2'], 100, ['eeg', 'eeg']), verbose='ERROR')
        raw.set_annotations(mne.Annotations([.5], [.1], ['stimulus']))
        raw.save(fif, fmt='double', verbose='ERROR')
        for ext in lab.EXPORTS + ['fif', 'edf', 'bdf']:
            result = convert(fif, ext)
            if ext == 'fif':
                restored = mne.io.read_raw_fif(result[0], verbose='ERROR')
                assert np.array_equal(restored.get_data(), raw.get_data())
                restored.close()

        vhdr = root / 'brain.vhdr'
        (root / 'brain.eeg').write_bytes(np.column_stack(channels[:1] * 2).astype('<f4').tobytes())
        vhdr.write_text('Brain Vision Data Exchange Header File Version 1.0\n[Common Infos]\nCodepage=UTF-8\nDataFile=brain.eeg\nMarkerFile=brain.vmrk\nDataFormat=BINARY\nDataOrientation=MULTIPLEXED\nNumberOfChannels=2\nSamplingInterval=10000\n[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n[Channel Infos]\nCh1=EEG1,,1,uV\nCh2=LFP,,1,uV\n', encoding='utf-8')
        (root / 'brain.vmrk').write_text('Brain Vision Data Exchange Marker File, Version 1.0\n[Common Infos]\nDataFile=brain.eeg\n[Marker Infos]\nMk1=Stimulus,S 1,51,10,0\n', encoding='utf-8')
        for ext in lab.EXPORTS + ['edf', 'bdf', 'fif']:
            result = convert(vhdr, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    assert np.allclose(restored['channel_0000'][:, 0], channels[0]*1e-6)
                    assert json.loads(restored['channel_0000'].attrs['metadata_json'])['units'] == 'V'

        from scipy.io import savemat
        eeglab = root / 'brain.set'
        savemat(eeglab, {'EEG': {'data': np.array([channels[0], channels[0]]), 'srate': 100., 'nbchan': 2,
            'pnts': 200, 'trials': 1, 'xmin': 0., 'xmax': 1.99, 'chanlocs': [{'labels': 'EEG1'}, {'labels': 'LFP'}]}})
        for ext in ('h5', 'npz', 'fif'):
            result = convert(eeglab, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    assert np.allclose(restored['channel_0000'][:, 0], channels[0]*1e-6)

        from pynwb import NWBFile, NWBHDF5IO, TimeSeries
        nwb = root / 'recording.nwb'
        document = NWBFile('Synthetic experiment', 'any2any-test', now)
        document.add_acquisition(TimeSeries(name='LFP', data=np.arange(100, dtype=float), unit='volts', rate=100., starting_time=2.))
        with NWBHDF5IO(nwb, 'w') as writer:
            writer.write(document)
        for ext in ('h5', 'npz', 'csv'):
            result = convert(nwb, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    key = next(iter(restored))
                    assert np.array_equal(restored[key][:, 0], np.arange(100, dtype=float))
                    meta = json.loads(restored[key].attrs['metadata_json'])
                    assert meta['sampling_rate_hz'] == 100. and meta['t_start_s'] == 2.

        import flowio
        fcs = root / 'cells.fcs'
        events = np.array([[1., 10.], [2., 20.], [3., 30.]], dtype='float32')
        with fcs.open('wb') as output:
            flowio.create_fcs(output, events.ravel().tolist(), ['FSC-A', 'FITC-A'])
        for ext in lab.EXPORTS:
            result = convert(fcs, ext)
            if ext == 'h5':
                with h5py.File(result[0]) as restored:
                    assert np.array_equal(restored['events_0000'][()], events)

        pdf = root / 'paper #%_{test}.pdf'
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((32, 50), 'Editable text with 5% and a_b & $c$ {test}.')
        image = np.zeros((4, 5, 3), dtype='uint8');image[:, :, 0] = 255
        page.insert_image(pymupdf.Rect(32, 100, 132, 180), stream=imagecodecs.png_encode(image))
        page = document.new_page();page.insert_text((32, 50), 'Second page.')
        document.save(pdf);document.close()
        for ext in ('tex', 'tex-layout', 'tex-layout'):
            result = convert(pdf, ext)[0]
            text = result.read_text(encoding='utf-8')
            assert text.count(r'\begin{document}') == 1 and text.count(r'\end{document}') == 1
            if ext == 'tex':
                assert r'5\%' in text and r'a\_b' in text and 'Second page.' in text
            else:
                linked = text.split('fitpaper=true]{')[1].split('}')[0]
                assert (out / linked).is_file() and all(char not in linked for char in '#%{} ')
                with pymupdf.open(out / linked) as restored:
                    assert len(restored) == 2 and 'Second page.' in restored[1].get_text()
        scanned = root / 'scanned.pdf'
        document = pymupdf.open();document.new_page().insert_image(pymupdf.Rect(0, 0, 100, 100), stream=imagecodecs.png_encode(image));document.save(scanned);document.close()
        before = set(out.iterdir())
        try:
            a.convert(scanned, 'tex', out)
        except ValueError as error:
            assert 'OCR' in str(error)
        else:
            raise AssertionError('Scanned PDF text export should request OCR.')
        assert before == set(out.iterdir())
        convert(scanned, 'tex-layout')
        cancel = threading.Event();cancel.set()
        before = set(out.iterdir())
        try:
            a.convert(abf, 'h5', out, cancel)
        except a.Cancelled:
            pass
        else:
            raise AssertionError('Cancellation was ignored.')
        assert before == set(out.iterdir())
        class CancelAfter:
            def __init__(self, count):
                self.remaining = count
            def is_set(self):
                self.remaining -= 1
                return self.remaining <= 0
        for source, ext in ((czi, 'tiff'), (abf, 'h5'), (edf, 'h5'), (fast5, 'h5'), (zipped, 'fasta')):
            before = set(out.iterdir())
            try:
                a.convert(source, ext, out, CancelAfter(4 if source != fast5 else 3))
            except a.Cancelled:
                pass
            else:
                raise AssertionError(f'Mid-conversion cancellation was ignored: {source}')
            assert set(out.iterdir()) == before
            probe = source.with_name(source.name + '.probe')
            source.rename(probe)
            probe.rename(source)

        assert 'tex (layout)' in a.FORMAT_LABELS.values()
    print(f'PASS: {checks} lab/image/genomic/LaTeX conversions plus metadata and safety checks.', flush=True)


if __name__ == '__main__':
    main()
