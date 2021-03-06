import torch
import pytorch_ctc as ctc
from torch.utils.ffi import _wrap_function
from ._ctc_decode import lib as _lib, ffi as _ffi

__all__ = []


def _import_symbols(locals):
    for symbol in dir(_lib):
        fn = getattr(_lib, symbol)
        new_symbol = "_" + symbol
        locals[new_symbol] = _wrap_function(fn, _ffi)
        __all__.append(new_symbol)


_import_symbols(locals())


class BaseCTCBeamDecoder(object):
    def __init__(self, labels, top_paths=1, beam_width=10, blank_index=0, space_index=28, merge_repeated=True):
        self._labels = labels
        self._top_paths = top_paths
        self._beam_width = beam_width
        self._blank_index = blank_index
        self._space_index = space_index
        self._merge_repeated = merge_repeated
        self._num_classes = len(labels)
        self._decoder = None

        if blank_index < 0 or blank_index >= self._num_classes:
            raise ValueError("blank_index must be within num_classes")

        if top_paths < 1 or top_paths > beam_width:
            raise ValueError("top_paths must be greater than 1 and less than or equal to the beam_width")

    def decode(self, probs, seq_len=None):
        prob_size = probs.size()
        max_seq_len = prob_size[0]
        batch_size = prob_size[1]
        num_classes = prob_size[2]

        if seq_len is not None and batch_size != seq_len.size(0):
            raise ValueError("seq_len shape must be a (batch_size) tensor or None")

        seq_len = torch.IntTensor(batch_size).zero_().add_(max_seq_len) if seq_len is None else seq_len
        output = torch.IntTensor(self._top_paths, batch_size, max_seq_len)
        scores = torch.FloatTensor(self._top_paths, batch_size)
        out_seq_len = torch.IntTensor(self._top_paths, batch_size)

        result = ctc._ctc_beam_decode(self._decoder, self._decoder_type, probs, seq_len, output, scores, out_seq_len)

        return output, scores, out_seq_len


class BaseScorer(object):
    def __init__(self):
        self._scorer_type = 0
        self._scorer = None

    def get_scorer_type(self):
        return self._scorer_type

    def get_scorer(self):
        return self._scorer


class Scorer(BaseScorer):
    def __init__(self):
        super(Scorer, self).__init__()
        self._scorer = ctc._get_base_scorer()


class KenLMScorer(BaseScorer):
    def __init__(self, labels, lm_path, trie_path, blank_index=0, space_index=28):
        super(KenLMScorer, self).__init__()
        if ctc._kenlm_enabled() != 1:
            raise ImportError("pytorch-ctc not compiled with KenLM support.")
        self._scorer_type = 1
        self._scorer = ctc._get_kenlm_scorer(labels, len(labels), space_index, blank_index, lm_path.encode(), trie_path.encode())

    def set_lm_weight(self, weight):
        if weight is not None:
            ctc._set_kenlm_scorer_lm_weight(self._scorer, weight)

    def set_word_weight(self, weight):
        if weight is not None:
            ctc._set_kenlm_scorer_wc_weight(self._scorer, weight)

    def set_valid_word_weight(self, weight):
        if weight is not None:
            ctc._set_kenlm_scorer_vwc_weight(self._scorer, weight)


class CTCBeamDecoder(BaseCTCBeamDecoder):
    def __init__(self, scorer, labels, top_paths=1, beam_width=10, blank_index=0, space_index=28, merge_repeated=True):
        super(CTCBeamDecoder, self).__init__(labels, top_paths=top_paths, beam_width=beam_width, blank_index=blank_index, space_index=space_index, merge_repeated=merge_repeated)
        merge_int = 1 if merge_repeated else 0
        self._scorer = scorer
        self._decoder_type = self._scorer.get_scorer_type()
        self._decoder = ctc._get_ctc_beam_decoder(self._num_classes, top_paths, beam_width, blank_index, merge_int, self._scorer.get_scorer(), self._decoder_type)


def generate_lm_trie(dictionary_path, kenlm_path, output_path, labels, blank_index=0, space_index=28):
    if ctc._kenlm_enabled() != 1:
        raise ImportError("pytorch-ctc not compiled with KenLM support.")
    result = ctc._generate_lm_trie(labels, len(labels), blank_index, space_index, kenlm_path.encode(), dictionary_path.encode(), output_path.encode())

    if result != 0:
        raise ValueError("Error encountered generating trie")
