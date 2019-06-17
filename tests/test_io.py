import os
import sys
import math
from array import array
from tempfile import NamedTemporaryFile, TemporaryDirectory
import filecmp
from unittest import TestCase
from genty import genty, genty_dataset
from test_util import _sample_generator, _generate_pure_tone, PURE_TONE_DICT
from auditok.io import (
    DATA_FORMAT,
    AudioIOError,
    AudioParameterError,
    BufferAudioSource,
    RawAudioSource,
    WaveAudioSource,
    StdinAudioSource,
    check_audio_data,
    _guess_audio_format,
    _normalize_use_channel,
    _get_audio_parameters,
    _array_to_bytes,
    _mix_audio_channels,
    _extract_selected_channel,
    _load_raw,
    _load_wave,
    _load_with_pydub,
    get_audio_source,
    from_file,
    _save_raw,
    _save_wave,
    _save_with_pydub,
    to_file,
)


if sys.version_info >= (3, 0):
    PYTHON_3 = True
    from unittest.mock import patch, Mock
else:
    PYTHON_3 = False
    from mock import patch, Mock

AUDIO_PARAMS_SHORT = {"sr": 16000, "sw": 2, "ch": 1}


@genty
class TestIO(TestCase):
    @genty_dataset(
        valid_mono=(b"\0" * 113, 1, 1),
        valid_stereo=(b"\0" * 160, 1, 2),
        invalid_mono_sw_2=(b"\0" * 113, 2, 1, False),
        invalid_stereo_sw_1=(b"\0" * 113, 1, 2, False),
        invalid_stereo_sw_2=(b"\0" * 158, 2, 2, False),
    )
    def test_check_audio_data(self, data, sample_width, channels, valid=True):

        if not valid:
            with self.assertRaises(AudioParameterError):
                check_audio_data(data, sample_width, channels)
        else:
            self.assertIsNone(check_audio_data(data, sample_width, channels))

    @genty_dataset(
        extention_and_format_same=("wav", "filename.wav", "wav"),
        extention_and_format_different=("wav", "filename.mp3", "wav"),
        extention_no_format=(None, "filename.wav", "wav"),
        format_no_extension=("wav", "filename", "wav"),
        no_format_no_extension=(None, "filename", None),
    )
    def test_guess_audio_format(self, fmt, filename, expected):
        result = _guess_audio_format(fmt, filename)
        self.assertEqual(result, expected)

    @genty_dataset(
        none=(None, 0),
        positive_int=(1, 0),
        left=("left", 0),
        right=("right", 1),
        mix=("mix", "mix"),
    )
    def test_normalize_use_channel(self, use_channel, expected):
        result = _normalize_use_channel(use_channel)
        self.assertEqual(result, expected)

    @genty_dataset(
        int_1=((8000, 2, 1, 1), (8000, 2, 1, 1)),
        int_2=((8000, 2, 1, 2), (8000, 2, 1, 2)),
        use_channel_left=((8000, 2, 1, "left"), (8000, 2, 1, "left")),
        use_channel_right=((8000, 2, 1, "right"), (8000, 2, 1, "right")),
        use_channel_mix=((8000, 2, 1, "mix"), (8000, 2, 1, "mix")),
        use_channel_None=((8000, 2, 2, None), (8000, 2, 2, None)),
        no_use_channel=((8000, 2, 2), (8000, 2, 2, None)),
    )
    def test_get_audio_parameters_short_params(self, values, expected):
        params = dict(zip(("sr", "sw", "ch", "uc"), values))
        result = _get_audio_parameters(params)
        self.assertEqual(result, expected)

    @genty_dataset(
        int_1=((8000, 2, 1, 1), (8000, 2, 1, 1)),
        int_2=((8000, 2, 1, 2), (8000, 2, 1, 2)),
        use_channel_left=((8000, 2, 1, "left"), (8000, 2, 1, "left")),
        use_channel_right=((8000, 2, 1, "right"), (8000, 2, 1, "right")),
        use_channel_mix=((8000, 2, 1, "mix"), (8000, 2, 1, "mix")),
        use_channel_None=((8000, 2, 2, None), (8000, 2, 2, None)),
        no_use_channel=((8000, 2, 2), (8000, 2, 2, None)),
    )
    def test_get_audio_parameters_long_params(self, values, expected):
        params = dict(
            zip(
                ("sampling_rate", "sample_width", "channels", "use_channel"),
                values,
            )
        )
        result = _get_audio_parameters(params)
        self.assertEqual(result, expected)

    @genty_dataset(simple=((8000, 2, 1, 1), (8000, 2, 1, 1)))
    def test_get_audio_parameters_long_params_shadow_short_ones(
        self, values, expected
    ):
        params = dict(
            zip(
                ("sampling_rate", "sample_width", "channels", "use_channel"),
                values,
            )
        )
        params.update(dict(zip(("sr", "sw", "ch", "uc"), "xxxx")))
        result = _get_audio_parameters(params)
        self.assertEqual(result, expected)

    @genty_dataset(
        str_sampling_rate=(("x", 2, 1, 0),),
        negative_sampling_rate=((-8000, 2, 1, 0),),
        str_sample_width=((8000, "x", 1, 0),),
        negative_sample_width=((8000, -2, 1, 0),),
        str_channels=((8000, 2, "x", 0),),
        negative_channels=((8000, 2, -1, 0),),
    )
    def test_get_audio_parameters_invalid(self, values):
        # TODO 0 or negative use_channel must raise AudioParameterError
        # change implementation, don't accept negative uc
        # hifglight everywhere in doc that uc must be positive
        params = dict(
            zip(
                ("sampling_rate", "sample_width", "channels", "use_channel"),
                values,
            )
        )
        with self.assertRaises(AudioParameterError):
            _get_audio_parameters(params)

    @genty_dataset(
        mono_1byte=([400], 1),
        stereo_1byte=([400, 600], 1),
        three_channel_1byte=([400, 600, 2400], 1),
        mono_2byte=([400], 2),
        stereo_2byte=([400, 600], 2),
        three_channel_2byte=([400, 600, 1150], 2),
        mono_4byte=([400], 4),
        stereo_4byte=([400, 600], 4),
        four_channel_2byte=([400, 600, 1150, 7220], 4),
    )
    def test_mix_audio_channels(self, frequencies, sample_width):
        sampling_rate = 16000
        sample_width = 2
        channels = len(frequencies)
        mono_channels = [
            _generate_pure_tone(
                freq,
                duration_sec=0.1,
                sampling_rate=sampling_rate,
                sample_width=sample_width,
            )
            for freq in frequencies
        ]
        fmt = DATA_FORMAT[sample_width]
        expected = _array_to_bytes(
            array(
                fmt,
                (sum(samples) // channels for samples in zip(*mono_channels)),
            )
        )
        data = _array_to_bytes(array(fmt, _sample_generator(*mono_channels)))
        mixed = _mix_audio_channels(data, channels, sample_width)
        self.assertEqual(mixed, expected)

    @genty_dataset(
        mono_1byte=([400], 1, 0),
        stereo_1byte_2st_channel=([400, 600], 1, 1),
        mono_2byte=([400], 2, 0),
        stereo_2byte_1st_channel=([400, 600], 2, 0),
        stereo_2byte_2nd_channel=([400, 600], 2, 1),
        three_channel_2byte_last_negative_idx=([400, 600, 1150], 2, -1),
        three_channel_2byte_2nd_negative_idx=([400, 600, 1150], 2, -2),
        three_channel_2byte_1st_negative_idx=([400, 600, 1150], 2, -3),
        three_channel_4byte_1st=([400, 600, 1150], 4, 0),
        three_channel_4byte_last_negative_idx=([400, 600, 1150], 4, -1),
    )
    def test_extract_selected_channel(
        self, frequencies, sample_width, use_channel
    ):

        mono_channels = [
            _generate_pure_tone(
                freq,
                duration_sec=0.1,
                sampling_rate=16000,
                sample_width=sample_width,
            )
            for freq in frequencies
        ]
        channels = len(frequencies)
        fmt = DATA_FORMAT[sample_width]
        expected = _array_to_bytes(mono_channels[use_channel])
        data = _array_to_bytes(array(fmt, _sample_generator(*mono_channels)))
        selected_channel = _extract_selected_channel(
            data, channels, sample_width, use_channel
        )
        self.assertEqual(selected_channel, expected)

    @genty_dataset(mono=([400],), three_channel=([600, 1150, 2400],))
    def test_extract_selected_channel_mix(self, frequencies):

        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]
        channels = len(frequencies)
        fmt = DATA_FORMAT[2]
        expected = _array_to_bytes(
            array(
                fmt,
                (sum(samples) // channels for samples in zip(*mono_channels)),
            )
        )
        data = _array_to_bytes(array(fmt, _sample_generator(*mono_channels)))
        selected_channel = _extract_selected_channel(data, channels, 2, "mix")
        self.assertEqual(selected_channel, expected)

    @genty_dataset(positive=(2,), negative=(-3,))
    def test_extract_selected_channel_invalid_use_channel(self, use_channel):
        with self.assertRaises(AudioParameterError):
            _extract_selected_channel(b"\0\0", 2, 2, use_channel)

    @genty_dataset(
        raw_with_audio_format=(
            "audio",
            "raw",
            "_load_raw",
            AUDIO_PARAMS_SHORT,
        ),
        raw_with_extension=(
            "audio.raw",
            None,
            "_load_raw",
            AUDIO_PARAMS_SHORT,
        ),
        wave_with_audio_format=("audio", "wave", "_load_wave"),
        wav_with_audio_format=("audio", "wave", "_load_wave"),
        wav_with_extension=("audio.wav", None, "_load_wave"),
        format_and_extension_both_given=("audio.dat", "wav", "_load_wave"),
        format_and_extension_both_given_b=("audio.raw", "wave", "_load_wave"),
        no_format_nor_extension=("audio", None, "_load_with_pydub"),
        other_formats_ogg=("audio.ogg", None, "_load_with_pydub"),
        other_formats_webm=("audio", "webm", "_load_with_pydub"),
    )
    def test_from_file(
        self, filename, audio_format, funtion_name, kwargs=None
    ):
        funtion_name = "auditok.io." + funtion_name
        if kwargs is None:
            kwargs = {}
        with patch(funtion_name) as patch_function:
            from_file(filename, audio_format, **kwargs)
        self.assertTrue(patch_function.called)

    def test_from_file_large_file_raw(self,):
        filename = "tests/data/test_16KHZ_mono_400Hz.raw"
        audio_source = from_file(
            filename,
            large_file=True,
            sampling_rate=16000,
            sample_width=2,
            channels=1,
        )
        self.assertIsInstance(audio_source, RawAudioSource)

    def test_from_file_large_file_wave(self,):
        filename = "tests/data/test_16KHZ_mono_400Hz.wav"
        audio_source = from_file(filename, large_file=True)
        self.assertIsInstance(audio_source, WaveAudioSource)

    def test_from_file_large_file_compressed(self,):
        filename = "tests/data/test_16KHZ_mono_400Hz.ogg"
        with self.assertRaises(AudioIOError):
            from_file(filename, large_file=True)

    @genty_dataset(
        missing_sampling_rate=("sr",),
        missing_sample_width=("sw",),
        missing_channels=("ch",),
    )
    def test_from_file_missing_audio_param(self, missing_param):
        with self.assertRaises(AudioParameterError):
            params = AUDIO_PARAMS_SHORT.copy()
            del params[missing_param]
            from_file("audio", audio_format="raw", **params)

    def test_from_file_no_pydub(self):
        with patch("auditok.io._WITH_PYDUB", False):
            with self.assertRaises(AudioIOError):
                from_file("audio", "mp3")

    @genty_dataset(
        raw_first_channel=("raw", 1, 400),
        raw_second_channel=("raw", 2, 800),
        raw_third_channel=("raw", 3, 1600),
        raw_left_channel=("raw", "left", 400),
        raw_right_channel=("raw", "right", 800),
        wav_first_channel=("wav", 1, 400),
        wav_second_channel=("wav", 2, 800),
        wav_third_channel=("wav", 3, 1600),
        wav_left_channel=("wav", "left", 400),
        wav_right_channel=("wav", "right", 800),
    )
    def test_from_file_multichannel_audio(
        self, audio_format, use_channel, frequency
    ):
        expected = PURE_TONE_DICT[frequency]
        filename = "tests/data/test_16KHZ_3channel_400-800-1600Hz.{}".format(
            audio_format
        )
        sample_width = 2
        audio_source = from_file(
            filename,
            sampling_rate=16000,
            sample_width=sample_width,
            channels=3,
            use_channel=use_channel,
        )
        fmt = DATA_FORMAT[sample_width]
        data = array(fmt, audio_source._buffer)
        self.assertEqual(data, expected)

    @genty_dataset(
        raw_mono=("raw", "mono_400Hz", (400,)),
        raw_3channel=("raw", "3channel_400-800-1600Hz", (400, 800, 1600)),
        wav_mono=("wav", "mono_400Hz", (400,)),
        wav_3channel=("wav", "3channel_400-800-1600Hz", (400, 800, 1600)),
    )
    def test_from_file_multichannel_audio_mix(
        self, audio_format, filename_suffix, frequencies
    ):
        sampling_rate = 16000
        sample_width = 2
        channels = len(frequencies)
        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]
        channels = len(frequencies)
        fmt = DATA_FORMAT[sample_width]
        expected = _array_to_bytes(
            array(
                fmt,
                (sum(samples) // channels for samples in zip(*mono_channels)),
            )
        )
        filename = "tests/data/test_16KHZ_{}.{}".format(
            filename_suffix, audio_format
        )
        audio_source = from_file(
            filename,
            use_channel="mix",
            sampling_rate=sampling_rate,
            sample_width=2,
            channels=channels,
        )
        mixed = audio_source._buffer
        self.assertEqual((mixed), expected)

    @patch("auditok.io._WITH_PYDUB", True)
    @patch("auditok.io.BufferAudioSource")
    @genty_dataset(
        ogg_first_channel=("ogg", 1, "from_ogg"),
        ogg_second_channel=("ogg", 2, "from_ogg"),
        ogg_mix=("ogg", "mix", "from_ogg"),
        ogg_default=("ogg", None, "from_ogg"),
        mp3_left_channel=("mp3", "left", "from_mp3"),
        mp3_right_channel=("mp3", "right", "from_mp3"),
        flac_first_channel=("flac", 1, "from_file"),
        flac_second_channel=("flac", 1, "from_file"),
        flv_left_channel=("flv", "left", "from_flv"),
        webm_right_channel=("webm", "right", "from_file"),
    )
    def test_from_file_multichannel_audio_compressed(
        self, audio_format, use_channel, function, *mocks
    ):
        filename = "audio.{}".format(audio_format)
        segment_mock = Mock()
        segment_mock.sample_width = 2
        segment_mock.channels = 2
        segment_mock._data = b"abcd"
        with patch("auditok.io._extract_selected_channel") as ext_mock:
            with patch(
                "auditok.io.AudioSegment.{}".format(function)
            ) as open_func:
                open_func.return_value = segment_mock
                from_file(filename, use_channel=use_channel)
                self.assertTrue(open_func.called)
                self.assertTrue(ext_mock.called)

                use_channel = {"left": 1, "right": 2, None: 1}.get(
                    use_channel, use_channel
                )
                if isinstance(use_channel, int):
                    # _extract_selected_channel will be called with a channel starting from 0
                    use_channel -= 1
                ext_mock.assert_called_with(
                    segment_mock._data,
                    segment_mock.channels,
                    segment_mock.sample_width,
                    use_channel,
                )

        with patch("auditok.io._extract_selected_channel") as ext_mock:
            with patch(
                "auditok.io.AudioSegment.{}".format(function)
            ) as open_func:
                segment_mock.channels = 1
                open_func.return_value = segment_mock
                from_file(filename, use_channel=use_channel)
                self.assertTrue(open_func.called)
                self.assertFalse(ext_mock.called)

    @patch("auditok.io._WITH_PYDUB", True)
    @patch("auditok.io.BufferAudioSource")
    @genty_dataset(
        ogg=("ogg", "from_ogg"),
        mp3=("mp3", "from_mp3"),
        flac=("flac", "from_file"),
    )
    def test_from_file_multichannel_audio_mix_compressed(
        self, audio_format, function, *mocks
    ):
        filename = "audio.{}".format(audio_format)
        segment_mock = Mock()
        segment_mock.sample_width = 2
        segment_mock.channels = 2
        segment_mock._data = b"abcd"
        with patch("auditok.io._mix_audio_channels") as mix_mock:
            with patch(
                "auditok.io.AudioSegment.{}".format(function)
            ) as open_func:
                open_func.return_value = segment_mock
                from_file(filename, use_channel="mix")
                self.assertTrue(open_func.called)
                mix_mock.assert_called_with(
                    segment_mock._data,
                    segment_mock.channels,
                    segment_mock.sample_width,
                )

    @genty_dataset(
        dafault_first_channel=(None, 400),
        first_channel=(1, 400),
        second_channel=(2, 800),
        third_channel=(3, 1600),
        negative_first_channel=(-3, 400),
        negative_second_channel=(-2, 800),
        negative_third_channel=(-1, 1600),
    )
    def test_load_raw(self, use_channel, frequency):
        filename = "tests/data/test_16KHZ_3channel_400-800-1600Hz.raw"
        if use_channel is not None:
            audio_source = _load_raw(
                filename,
                sampling_rate=16000,
                sample_width=2,
                channels=3,
                use_channel=use_channel,
            )
        else:
            audio_source = _load_raw(
                filename, sampling_rate=16000, sample_width=2, channels=3
            )
        self.assertIsInstance(audio_source, BufferAudioSource)
        self.assertEqual(audio_source.sampling_rate, 16000)
        self.assertEqual(audio_source.sample_width, 2)
        self.assertEqual(audio_source.channels, 1)
        # generate a pure sine wave tone of the given frequency
        expected = PURE_TONE_DICT[frequency]
        # compre with data read from file
        fmt = DATA_FORMAT[2]
        data = array(fmt, audio_source._buffer)
        self.assertEqual(data, expected)

    @genty_dataset(
        mono=("mono_400Hz", (400,)),
        three_channel=("3channel_400-800-1600Hz", (400, 800, 1600)),
    )
    def test_load_raw_mix(self, filename_suffix, frequencies):
        sampling_rate = 16000
        sample_width = 2
        channels = len(frequencies)
        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]

        fmt = DATA_FORMAT[sample_width]
        expected = _array_to_bytes(
            array(
                fmt,
                (sum(samples) // channels for samples in zip(*mono_channels)),
            )
        )
        filename = "tests/data/test_16KHZ_{}.raw".format(filename_suffix)
        audio_source = _load_raw(
            filename,
            use_channel="mix",
            sampling_rate=sampling_rate,
            sample_width=2,
            channels=channels,
        )
        mixed = audio_source._buffer
        self.assertEqual(mixed, expected)
        self.assertIsInstance(audio_source, BufferAudioSource)
        self.assertEqual(audio_source.sampling_rate, sampling_rate)
        self.assertEqual(audio_source.sample_width, sample_width)
        self.assertEqual(audio_source.channels, 1)

    @genty_dataset(
        missing_sampling_rate=("sr",),
        missing_sample_width=("sw",),
        missing_channels=("ch",),
    )
    def test_load_raw_missing_audio_param(self, missing_param):
        with self.assertRaises(AudioParameterError):
            params = AUDIO_PARAMS_SHORT.copy()
            del params[missing_param]
            srate, swidth, channels, _ = _get_audio_parameters(params)
            _load_raw("audio", srate, swidth, channels)

    @genty_dataset(
        dafault_first_channel=(None, 400),
        first_channel=(1, 400),
        second_channel=(2, 800),
        third_channel=(3, 1600),
        negative_first_channel=(-3, 400),
        negative_second_channel=(-2, 800),
        negative_third_channel=(-1, 1600),
    )
    def test_load_wave(self, use_channel, frequency):
        filename = "tests/data/test_16KHZ_3channel_400-800-1600Hz.wav"
        if use_channel is not None:
            audio_source = _load_wave(filename, use_channel=use_channel)
        else:
            audio_source = _load_wave(filename)
        self.assertIsInstance(audio_source, BufferAudioSource)
        self.assertEqual(audio_source.sampling_rate, 16000)
        self.assertEqual(audio_source.sample_width, 2)
        self.assertEqual(audio_source.channels, 1)
        # generate a pure sine wave tone of the given frequency
        expected = PURE_TONE_DICT[frequency]
        # compre with data read from file
        fmt = DATA_FORMAT[2]
        data = array(fmt, audio_source._buffer)
        self.assertEqual(data, expected)

    @genty_dataset(
        mono=("mono_400Hz", (400,)),
        three_channel=("3channel_400-800-1600Hz", (400, 800, 1600)),
    )
    def test_load_wave_mix(self, filename_suffix, frequencies):
        sampling_rate = 16000
        sample_width = 2
        channels = len(frequencies)
        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]
        fmt = DATA_FORMAT[sample_width]
        expected = _array_to_bytes(
            array(
                fmt,
                (sum(samples) // channels for samples in zip(*mono_channels)),
            )
        )
        filename = "tests/data/test_16KHZ_{}.wav".format(filename_suffix)
        audio_source = _load_wave(filename, use_channel="mix")
        mixed = audio_source._buffer
        self.assertEqual(mixed, expected)
        self.assertIsInstance(audio_source, BufferAudioSource)
        self.assertEqual(audio_source.sampling_rate, sampling_rate)
        self.assertEqual(audio_source.sample_width, sample_width)
        self.assertEqual(audio_source.channels, 1)

    @patch("auditok.io._WITH_PYDUB", True)
    @patch("auditok.io.BufferAudioSource")
    @genty_dataset(
        ogg_default_first_channel=("ogg", 2, None, "from_ogg"),
        ogg_first_channel=("ogg", 1, 0, "from_ogg"),
        ogg_second_channel=("ogg", 2, 1, "from_ogg"),
        ogg_mix_channels=("ogg", 3, "mix", "from_ogg"),
        mp3_left_channel=("mp3", 1, "left", "from_mp3"),
        mp3_right_channel=("mp3", 2, "right", "from_mp3"),
        mp3_mix_channels=("mp3", 3, "mix", "from_mp3"),
        flac_first_channel=("flac", 2, 1, "from_file"),
        flac_second_channel=("flac", 2, 1, "from_file"),
        flv_left_channel=("flv", 1, "left", "from_flv"),
        webm_right_channel=("webm", 2, "right", "from_file"),
        webm_mix_channels=("webm", 4, "mix", "from_file"),
    )
    def test_load_with_pydub(
        self, audio_format, channels, use_channel, function, *mocks
    ):
        filename = "audio.{}".format(audio_format)
        segment_mock = Mock()
        segment_mock.sample_width = 2
        segment_mock.channels = channels
        segment_mock._data = b"abcdefgh"
        with patch("auditok.io._extract_selected_channel") as ext_mock:
            with patch(
                "auditok.io.AudioSegment.{}".format(function)
            ) as open_func:
                open_func.return_value = segment_mock
                normalized_use_channel = {"left": 1, "right": 2, None: 0}.get(
                    use_channel, use_channel
                )
                if isinstance(normalized_use_channel, int) and normalized_use_channel > 0:
                     normalized_use_channel -= 1
                _load_with_pydub(filename, audio_format, use_channel)
                self.assertTrue(open_func.called)
                if channels > 1:
                    self.assertTrue(ext_mock.called)
                    ext_mock.assert_called_with(
                        segment_mock._data,
                        segment_mock.channels,
                        segment_mock.sample_width,
                        normalized_use_channel,
                    )
                else:
                    self.assertFalse(ext_mock.called)

    @genty_dataset(
        mono=("mono_400Hz.raw", (400,)),
        three_channel=("3channel_400-800-1600Hz.raw", (400, 800, 1600)),
    )
    def test_save_raw(self, filename, frequencies):
        filename = "tests/data/test_16KHZ_{}".format(filename)
        sample_width = 2
        fmt = DATA_FORMAT[sample_width]
        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]
        data = _array_to_bytes(array(fmt, _sample_generator(*mono_channels)))
        tmpfile = NamedTemporaryFile()
        _save_raw(data, tmpfile.name)
        self.assertTrue(filecmp.cmp(tmpfile.name, filename, shallow=False))

    @genty_dataset(
        mono=("mono_400Hz.wav", (400,)),
        three_channel=("3channel_400-800-1600Hz.wav", (400, 800, 1600)),
    )
    def test_save_wave(self, filename, frequencies):
        filename = "tests/data/test_16KHZ_{}".format(filename)
        sampling_rate = 16000
        sample_width = 2
        channels = len(frequencies)
        fmt = DATA_FORMAT[sample_width]
        mono_channels = [PURE_TONE_DICT[freq] for freq in frequencies]
        data = _array_to_bytes(array(fmt, _sample_generator(*mono_channels)))
        tmpfile = NamedTemporaryFile()
        _save_wave(data, tmpfile.name, sampling_rate, sample_width, channels)
        self.assertTrue(filecmp.cmp(tmpfile.name, filename, shallow=False))

    @genty_dataset(
        missing_sampling_rate=("sr",),
        missing_sample_width=("sw",),
        missing_channels=("ch",),
    )
    def test_save_wave_missing_audio_param(self, missing_param):
        with self.assertRaises(AudioParameterError):
            params = AUDIO_PARAMS_SHORT.copy()
            del params[missing_param]
            srate, swidth, channels, _ = _get_audio_parameters(params)
            _save_wave(b"\0\0", "audio", srate, swidth, channels)

    def test_save_with_pydub(self):
        with patch("auditok.io.AudioSegment.export") as export:
            tmpdir = TemporaryDirectory()
            filename = os.path.join(tmpdir.name, "audio.ogg")
            _save_with_pydub(b"\0\0", filename, "ogg", 16000, 2, 1)
            self.assertTrue(export.called)
            tmpdir.cleanup()

    @genty_dataset(
        raw_with_audio_format=("audio", "raw"),
        raw_with_extension=("audio.raw", None),
        raw_with_audio_format_and_extension=("audio.mp3", "raw"),
        raw_no_audio_format_nor_extension=("audio", None),
    )
    def test_to_file_raw(self, filename, audio_format):
        exp_filename = "tests/data/test_16KHZ_mono_400Hz.raw"
        tmpdir = TemporaryDirectory()
        filename = os.path.join(tmpdir.name, filename)
        data = _array_to_bytes(PURE_TONE_DICT[400])
        to_file(data, filename, audio_format=audio_format)
        self.assertTrue(filecmp.cmp(filename, exp_filename, shallow=False))
        tmpdir.cleanup()

    @genty_dataset(
        wav_with_audio_format=("audio", "wav"),
        wav_with_extension=("audio.wav", None),
        wav_with_audio_format_and_extension=("audio.mp3", "wav"),
        wave_with_audio_format=("audio", "wave"),
        wave_with_extension=("audio.wave", None),
        wave_with_audio_format_and_extension=("audio.mp3", "wave"),
    )
    def test_to_file_wave(self, filename, audio_format):
        exp_filename = "tests/data/test_16KHZ_mono_400Hz.wav"
        tmpdir = TemporaryDirectory()
        filename = os.path.join(tmpdir.name, filename)
        data = _array_to_bytes(PURE_TONE_DICT[400])
        to_file(
            data,
            filename,
            audio_format=audio_format,
            sampling_rate=16000,
            sample_width=2,
            channels=1,
        )
        self.assertTrue(filecmp.cmp(filename, exp_filename, shallow=False))
        tmpdir.cleanup()

    @genty_dataset(
        missing_sampling_rate=("sr",),
        missing_sample_width=("sw",),
        missing_channels=("ch",),
    )
    def test_to_file_missing_audio_param(self, missing_param):
        params = AUDIO_PARAMS_SHORT.copy()
        del params[missing_param]
        with self.assertRaises(AudioParameterError):
            to_file(b"\0\0", "audio", audio_format="wav", **params)
        with self.assertRaises(AudioParameterError):
            to_file(b"\0\0", "audio", audio_format="mp3", **params)

    def test_to_file_no_pydub(self):
        with patch("auditok.io._WITH_PYDUB", False):
            with self.assertRaises(AudioIOError):
                to_file("audio", b"", "mp3")

    @patch("auditok.io._WITH_PYDUB", True)
    @genty_dataset(
        ogg_with_extension=("audio.ogg", None),
        ogg_with_audio_format=("audio", "ogg"),
        ogg_format_with_wrong_extension=("audio.wav", "ogg"),
    )
    def test_to_file_compressed(self, filename, audio_format, *mocks):
        with patch("auditok.io.AudioSegment.export") as export:
            tmpdir = TemporaryDirectory()
            filename = os.path.join(tmpdir.name, filename)
            to_file(b"\0\0", filename, audio_format, **AUDIO_PARAMS_SHORT)
            self.assertTrue(export.called)
            tmpdir.cleanup()

    @genty_dataset(
        string_wave=(
            "tests/data/test_16KHZ_mono_400Hz.wav",
            BufferAudioSource,
        ),
        string_wave_large_file=(
            "tests/data/test_16KHZ_mono_400Hz.wav",
            WaveAudioSource,
            {"large_file": True},
        ),
        stdin=("-", StdinAudioSource),
        string_raw=("tests/data/test_16KHZ_mono_400Hz.raw", BufferAudioSource),
        string_raw_large_file=(
            "tests/data/test_16KHZ_mono_400Hz.raw",
            RawAudioSource,
            {"large_file": True},
        ),
        bytes_=(b"0" * 8000, BufferAudioSource),
    )
    def test_get_audio_source(self, input, expected_type, extra_args=None):
        kwargs = {"sampling_rate": 16000, "sample_width": 2, "channels": 1}
        if extra_args is not None:
            kwargs.update(extra_args)
        audio_source = get_audio_source(input, **kwargs)
        self.assertIsInstance(audio_source, expected_type)