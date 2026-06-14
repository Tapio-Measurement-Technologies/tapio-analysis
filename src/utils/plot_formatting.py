import math

from matplotlib.ticker import Formatter


def _strip_trailing_zeroes(text):
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _normalize_scientific_notation(text):
    mantissa, exponent = text.lower().split("e")
    mantissa = _strip_trailing_zeroes(mantissa)
    return f"{mantissa}e{int(exponent)}"


def compact_number_label(value, max_chars=5):
    """Format a tick label compactly without rounding small values to zero."""
    if not math.isfinite(value):
        return str(value)

    max_chars = max(1, int(max_chars))
    if value == 0:
        return "0"

    abs_value = abs(value)
    fixed_lower_limit = 10 ** -(max_chars - 2)
    fixed_upper_limit = 10 ** max_chars
    use_scientific = abs_value < fixed_lower_limit or abs_value >= fixed_upper_limit

    if not use_scientific:
        for decimals in range(max_chars, -1, -1):
            label = _strip_trailing_zeroes(f"{value:.{decimals}f}")
            if label == "0":
                continue
            if len(label) <= max_chars:
                return label

    for precision in range(max_chars - 1, -1, -1):
        label = _normalize_scientific_notation(f"{value:.{precision}e}")
        if len(label) <= max_chars:
            return label

    return _normalize_scientific_notation(f"{value:.0e}")


class CompactNumberFormatter(Formatter):
    """Compact formatter that avoids collapsing nearby tick labels together."""

    def __init__(self, max_chars=5, extra_precision_chars=2, pad_labels=True):
        self.max_chars = max(1, int(max_chars))
        self.extra_precision_chars = max(0, int(extra_precision_chars))
        self.pad_labels = pad_labels
        self.style = "fixed"
        self.precision = 0
        self.label_width = 0
        self.minimum_label_width = 0

    def set_locs(self, locs):
        self.locs = locs
        finite_locs = [loc for loc in locs if math.isfinite(loc)]
        if not finite_locs:
            self.style = "fixed"
            self.precision = 0
            self.label_width = 0
            return

        nonzero_locs = [loc for loc in finite_locs if loc != 0]
        if not nonzero_locs:
            self.style = "fixed"
            self.precision = 0
            self.label_width = 1
            return

        min_abs = min(abs(loc) for loc in nonzero_locs)
        max_abs = max(abs(loc) for loc in nonzero_locs)
        styles = (
            ["scientific", "fixed"]
            if min_abs < 0.01 or max_abs >= 100000
            else ["fixed", "scientific"]
        )

        max_allowed_chars = self.max_chars + self.extra_precision_chars
        fallback = ("scientific", max_allowed_chars)

        for allowed_chars in range(self.max_chars, max_allowed_chars + 1):
            for style in styles:
                for precision in range(0, 8):
                    labels = [
                        self._format_with_style(loc, style, precision)
                        for loc in finite_locs
                    ]
                    if max(len(label) for label in labels) > allowed_chars:
                        continue
                    if self._labels_preserve_tick_values(finite_locs, labels):
                        self.style = style
                        self.precision = precision
                        self._set_label_width(finite_locs)
                        return
                    fallback = (style, precision)

        self.style, self.precision = fallback
        self._set_label_width(finite_locs)

    def __call__(self, value, position=None):
        label = self._format_with_style(value, self.style, self.precision)
        label_width = max(self.label_width, self.minimum_label_width)
        if self.pad_labels and label_width:
            return label.rjust(label_width)
        return label

    def set_minimum_label_width(self, label_width):
        self.minimum_label_width = max(0, int(label_width))

    def _set_label_width(self, locs):
        if not self.pad_labels:
            self.label_width = 0
            return

        labels = [
            self._format_with_style(loc, self.style, self.precision)
            for loc in locs
        ]
        self.label_width = max(len(label) for label in labels)

    def _format_with_style(self, value, style, precision):
        if not math.isfinite(value):
            return str(value)
        if value == 0:
            return "0"
        if style == "scientific":
            return _normalize_scientific_notation(f"{value:.{precision}e}")
        return _strip_trailing_zeroes(f"{value:.{precision}f}")

    @staticmethod
    def _labels_preserve_tick_values(values, labels):
        for value, label in zip(values, labels):
            if value != 0 and label == "0":
                return False
        return len(set(labels)) == len(set(values))


def apply_compact_tick_formatting(ax, max_chars=5, x_axis=True, y_axis=True):
    formatters = []

    if x_axis:
        formatter = CompactNumberFormatter(max_chars)
        formatter.set_locs(ax.xaxis.get_majorticklocs())
        ax.xaxis.set_major_formatter(formatter)
        formatters.append(formatter)
        for label in ax.get_xticklabels():
            label.set_fontfamily("monospace")
    if y_axis:
        formatter = CompactNumberFormatter(max_chars)
        formatter.set_locs(ax.yaxis.get_majorticklocs())
        ax.yaxis.set_major_formatter(formatter)
        formatters.append(formatter)
        for label in ax.get_yticklabels():
            label.set_fontfamily("monospace")

    return formatters
