#!/usr/bin/env python

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
import matplotlib.colors as colors
from utils.filters import bandpass_filter

tape_channel = "Caliper"

figsize = (7, 3)
lowcut = 0.001
highcut = 50
end_pros = 0.1
tape_width_mm = 40


class DataLoader():

    def __init__(self, fn, tape_channel="Caliper"):
        self.df = self.load_df_from_txt(fn)
        self.tape_channel = tape_channel
        self.peaks = self.get_peaks(self.tape_channel)

    def load_df_from_txt(self, fn):
        with open(fn, 'r', encoding='ISO-8859-1') as f:
            for line in f:
                if '[Raw signal]' in line:
                    break

            df = pd.read_csv(f, sep='\t')

        return df

    def get_peaks(self, tape_channel):

        peaks, _ = find_peaks(self.df[tape_channel][2:], distance=100,
                              height=110)  # Adjust distance and height as needed
        return peaks

    def get_unit(self, channel):
        return self.df[channel][0]

    def calculate_variances(self, segments):
        k, p = segments.shape  # Number of samples in MD and CD, respectively
        overall_mean = np.mean(segments)

        md_means = np.mean(segments, axis=1)
        cd_means = np.mean(segments, axis=0)

        Sa2 = np.sum((md_means - overall_mean)**2) / (k - 1)
        Sb2 = np.sum((cd_means - overall_mean)**2) / (p - 1)

        total_variance = np.sum((segments - overall_mean)**2) / (k * p - 1)

        residuals = segments - md_means[:, None] - cd_means + overall_mean
        residual_variance = np.sum(residuals**2) / ((k - 1) * (p - 1))

        md_variance = Sa2 - (1 / p) * residual_variance
        cd_variance = Sb2 - (1 / k) * residual_variance

        return total_variance, md_variance, cd_variance, residual_variance

    def calculate_residuals_and_variance(self, segments, md_variance, cd_variance):
        residuals = segments - np.mean(segments, axis=1, keepdims=True) - np.mean(segments, axis=0,
                                                                                  keepdims=True) + np.mean(segments)
        residual_variance = np.mean(residuals**2)
        return residuals, residual_variance

    def get_vca_stats(self, channel):
        self.prepare_segments(channel)
        vca_stats = {}
        total, md, cd, res = self.calculate_variances(self.segments)
        vca_stats["md_std_dev"] = np.sqrt(md)
        vca_stats["cd_std_dev"] = np.sqrt(cd)
        vca_stats["total_std_dev"] = np.sqrt(total)
        vca_stats["residual_std_dev"] = np.sqrt(res)

        mean = np.mean(self.mean_segment)

        vca_stats["md_std_dev_p"] = 100 * vca_stats["md_std_dev"] / mean
        vca_stats["cd_std_dev_p"] = 100 * vca_stats["cd_std_dev"] / mean
        vca_stats["total_std_dev_p"] = 100 * vca_stats["total_std_dev"] / mean
        vca_stats["residual_std_dev_p"] = 100 * vca_stats["residual_std_dev"] / mean

        total, md, cd, res = self.calculate_variances(self.segments_no_ends)
        vca_stats["le_md_std_dev"] = np.sqrt(md)
        vca_stats["le_cd_std_dev"] = np.sqrt(cd)
        vca_stats["le_total_std_dev"] = np.sqrt(total)
        vca_stats["le_residual_std_dev"] = np.sqrt(res)

        vca_stats["le_md_std_dev_p"] = 100 * vca_stats["le_md_std_dev"] / mean
        vca_stats["le_cd_std_dev_p"] = 100 * vca_stats["le_cd_std_dev"] / mean
        vca_stats["le_total_std_dev_p"] = 100 * vca_stats["le_total_std_dev"] / mean
        vca_stats["le_residual_std_dev_p"] = 100 * vca_stats["le_residual_std_dev"] / mean

        return vca_stats

    def get_stats(self, channel):
        self.prepare_segments(channel)
        stats = {}

        # Calculate stats
        stats['mean'] = np.mean(self.mean_segment)
        stats['min'] = np.min(self.mean_segment)
        stats['max'] = np.max(self.mean_segment)
        stats['pp'] = np.max(self.mean_segment) - np.min(self.mean_segment)
        stats['std_dev'] = np.std(self.mean_segment)

        # Calculate stats relative to mean
        stats['mean_p'] = 100 * stats['mean'] / stats['mean']
        stats['min_p'] = 100 * stats['min'] / stats['mean']
        stats['max_p'] = 100 * stats['max'] / stats['mean']
        stats['pp_p'] = 100 * stats['pp'] / stats['mean']
        stats['std_dev_p'] = 100 * stats['std_dev'] / stats['mean']

        # Calculate stats no ends
        stats['le_mean'] = np.mean(self.mean_segment_no_ends)
        stats['le_min'] = np.min(self.mean_segment_no_ends)
        stats['le_max'] = np.max(self.mean_segment_no_ends)
        stats['le_pp'] = np.max(self.mean_segment_no_ends) - np.min(self.mean_segment_no_ends)
        stats['le_std_dev'] = np.std(self.mean_segment_no_ends)

        # Calculate stats no ends relative to mean
        stats['le_mean_p'] = 100 * stats['le_mean'] / stats['le_mean']
        stats['le_min_p'] = 100 * stats['le_min'] / stats['le_mean']
        stats['le_max_p'] = 100 * stats['le_max'] / stats['le_mean']
        stats['le_pp_p'] = 100 * stats['le_pp'] / stats['le_mean']
        stats['le_std_dev_p'] = 100 * stats['le_std_dev'] / stats['le_mean']
        return stats

    def get_mean(self, channel):
        self.prepare_segments(channel)
        return np.mean(self.segments)

    def prepare_segments(self, channel):
        df = self.df
        # Drop the first row and convert all columns to float
        unit = df[channel][0]
        self.unit = unit
        df = df.drop(df.index[0]).astype(float)

        signal = df[channel]

        array = df['x'].values
        array = df[channel].to_numpy()

        vals = [i for i in df['x']]
        m_per_sample = ((vals[-1] - vals[0]) / len(vals))

        plt.figure(figsize=figsize)
        plt.plot(df['x'], df[channel], label=channel)

        for peak in self.peaks:
            plt.axvline(x=df['x'].iloc[peak], color='r')

        plt.xlabel('Distance [m]')
        plt.ylabel(channel)
        plt.title('Raw data ({}) and detected peaks ({})'.format(channel, tape_channel))
        plt.tight_layout()

        segments = []
        peaks = self.peaks

        for i in range(len(peaks) - 1):
            segment = df[channel].iloc[peaks[i]:peaks[i + 1]].values
            segments.append(segment)

        # # Determine the minimum length of all segments
        min_length = min(len(seg) for seg in segments)
        max_length = max(len(seg) for seg in segments)
        diff = max_length - min_length
        diff_mm = diff * m_per_sample * 1000
        print(m_per_sample)

        print("Segments length difference {} samples = {:.2f} mm".format(diff, diff_mm))

        # # Discard data from both ends of longer segments
        # Discard samples half tape width from both ends
        discard = int(tape_width_mm / 1000 / m_per_sample / 2)
        print(discard)

        segments = [seg[(len(seg) - min_length) // 2:(len(seg) + min_length) // 2] for seg in segments]

        segments = [seg[discard:-1 * discard] for seg in segments]

        fs = 1 / m_per_sample
        self.unfiltered_segments = segments
        segments = [bandpass_filter(seg, lowcut, highcut, fs) for seg in segments]

        end_samples = int(min_length * end_pros)
        segments_no_ends = [seg[end_samples:-1 * end_samples] for seg in segments]

        self.segments = np.array(segments)
        self.segments_no_ends = np.array(segments_no_ends)

        self.mean_segment = np.mean(segments, axis=0)
        self.mean_segment_no_ends = np.mean(segments_no_ends, axis=0)

        self.min_segment = np.min(segments, axis=0)
        self.max_segment = np.max(segments, axis=0)
        self.m_per_sample = m_per_sample

    def get_bw_tr_calib_func(self):
        pass

    def formation(self):

        def calculate_formation_index(arr, window_size=400):
            arr = np.array(arr)
            num_values = len(arr) - window_size + 1
            result = np.empty(num_values)

            for i in range(num_values):
                window = arr[i:i + window_size]
                variance = np.var(window)
                sqrt_mean = np.sqrt(np.mean(window))
                result[i] = variance / sqrt_mean if sqrt_mean != 0 else 0

            return result

        def sx(segment):
            # Specific formation calculation
            return np.var(segment) / np.mean(segment)

        self.prepare_segments("Basis Weight 2")
        bw_segments = np.array(self.unfiltered_segments)
        bw_segments = np.array(self.segments)
        bw_mean_segment = self.mean_segment
        self.prepare_segments("Transmission")
        transmission_segments = np.array(self.unfiltered_segments)
        transmission_segments = np.array(self.segments)
        transmission_mean_segment = self.mean_segment
        plt.figure(figsize=figsize)

        self.prepare_segments("Basis Weight 2")
        bw2_segments = np.array(self.unfiltered_segments)
        bw2_segments = np.array(self.segments)
        bw2_mean_segment = self.mean_segment

        # for i in range(len(bw_segments)):
        #     print(i)
        #     plt.title("Basis weight and transmission correlation")
        #     plt.ylabel("Transmission")
        #     plt.xlabel("Basis weight")
        #     plt.scatter(bw_segments[i], transmission_segments[i], lw=0.2, color="black")

        from scipy.optimize import curve_fit

        def linear(x, a, b):
            return a * x + b

        params, covariance = curve_fit(linear, transmission_segments.flatten(), bw_segments.flatten())

        def f(x):
            return linear(x, *params)

        vectorized_function = np.vectorize(f)
        seg_index = 1
        res = vectorized_function(transmission_segments[seg_index])
        plt.figure()
        plt.plot(res, label="Transmission (calibrated to Basis weight 1)")
        plt.plot(bw_segments[seg_index], label="Basis Weight 1")
        plt.plot(bw2_segments[seg_index], label="Basis Weight 2")
        plt.grid()

        plt.legend()

        tr_fi = calculate_formation_index(res)
        bw_fi = calculate_formation_index(bw_segments[seg_index])
        plt.figure()
        plt.plot(tr_fi, label="Formation index (Transmission)")
        plt.plot(bw_fi, label="Formation index (Basis weight 1)")
        plt.legend()

        plt.show()

    def plot_data_cd(self, plot_channel):
        self.prepare_segments(plot_channel)
        # plt.show()

        ## CD Profile plot
        cd_profile_fig, ax = plt.subplots(figsize=figsize)

        x_data = np.linspace(0, self.mean_segment.size * self.m_per_sample, self.mean_segment.size)
        # Plot with grid, title and labels
        ax.plot(x_data,
                self.mean_segment,
                color='tab:green',
                linewidth=1,
                label="Mean ({} profiles)".format(len(self.segments)))

        ax.plot(x_data, self.max_segment, color='tab:red', linewidth=0.5, linestyle='--', label='Max', alpha=0.5)
        ax.plot(x_data, self.min_segment, color='tab:blue', linewidth=0.5, linestyle='--', label='Min', alpha=0.5)

        ax.grid(True)
        ax.legend(loc="upper right")
        # ax.set_title("{} CD Profile".format(plot_channel), fontsize=14, fontweight='bold')
        ax.set_xlabel('Distance [m]', fontsize=12)
        ax.set_ylabel("{} [{}]".format(plot_channel, self.unit), fontsize=12)

        # Plot the heatmap

        cmap = plt.get_cmap('viridis')
        print(self.segments.min())
        print(self.segments.max())
        norm = colors.Normalize(vmin=self.mean_segment.min(), vmax=self.mean_segment.max())
        xmin, xmax = x_data[0], x_data[-1]
        ymin, ymax = 0, self.segments.shape[0]
        plt.tight_layout()

        # Colormap plot

        colormap_fig, ((_, cd_profile_ax), (md_mean_ax, ax2), (ax3, ax4),
                       (ax5, ax6)) = plt.subplots(4,
                                                  2,
                                                  figsize=(7, 6.7),
                                                  gridspec_kw={
                                                      'width_ratios': [1, 5],
                                                      'height_ratios': [1, 4, 4, 1]
                                                  })
        # plt.subplots_adjust(wspace=0, hspace=0.1)

        for a in [_, ax3, ax5]:
            a.grid(False)
            a.axis('off')
            a.set_xticks([])
            a.set_yticks([])

        # Plot for sample mean on md_mean_ax
        md_mean = np.mean(self.segments, axis=1)
        md_mean_y = np.arange(len(md_mean))

        md_mean_ax.plot(md_mean, md_mean_y, color='tab:blue', linewidth=2)
        md_mean_ax.set_ylim(np.min(md_mean_y), np.max(md_mean_y))

        md_mean_ax.grid(True)

        cd_profile_ax.grid(True)
        cd_profile_ax.set_xlabel("Distance [m]")
        cd_profile_ax.set_ylabel("CD Mean [{}]".format(self.unit))

        cd_profile_ax.xaxis.set_ticks_position('top')
        cd_profile_ax.xaxis.set_label_position('top')
        cd_profile_ax.plot(x_data, self.mean_segment)

        heatmap_pos = ax2.get_position()
        cd_profile_pos = cd_profile_ax.get_position()
        print("--")
        print(cd_profile_pos)
        print(heatmap_pos.width)
        print("--")

        cd_profile_ax.set_position([cd_profile_pos.x0, cd_profile_pos.y0, 0.471, 0.1])
        cd_profile_ax.set_xlim(np.min(x_data), np.max(x_data))

        md_mean_ax.set_xlabel("MD Mean [{}]".format(self.unit))
        md_mean_ax.set_ylabel("Sample index")

        # Existing plot for heatmap on ax2
        cmap = plt.get_cmap('viridis')
        norm = colors.Normalize(vmin=self.mean_segment.min(), vmax=self.mean_segment.max())

        cax = ax2.imshow(self.segments,
                         aspect='auto',
                         origin='lower',
                         cmap=cmap,
                         norm=norm,
                         extent=[xmin, xmax, ymin, ymax])
        colorbar = colormap_fig.colorbar(cax, ax=ax2)
        colorbar.set_label("Measured value [{}]".format(self.unit))

        ax2.set_xlabel("Distance [m]")

        residuals, _ = self.calculate_residuals_and_variance(self.segments, 0, 0)

        norm = colors.Normalize(vmin=residuals.min(), vmax=residuals.max())

        cax = ax4.imshow(residuals,
                         aspect='auto',
                         origin='lower',
                         cmap=cmap,
                         norm=norm,
                         extent=[xmin, xmax, ymin, ymax])

        colorbar = colormap_fig.colorbar(cax, ax=ax4)
        colorbar.set_label("Residual variation [{}]".format(self.unit))

        # ax4.set_title("Residual variation")
        ax4.set_ylabel("Sample index")

        residual_profile_pos = ax6.get_position()
        ax6.set_position([residual_profile_pos.x0, residual_profile_pos.y0 - 0.03, 0.471, 0.1])
        ax6.set_ylabel("Residual\nvariation [{}]".format(self.unit))
        ax6.set_xlim(np.min(x_data), np.max(x_data))

        ax6.plot(x_data, np.mean(residuals, axis=0))
        ax6.set_xlabel("Distance [m]")

        # Layout adjustments
        # plt.tight_layout()

        ## CD spectrum

        cd_spectrum_fig, ax = plt.subplots(figsize=figsize)

        ax.grid(True)

        fft_results = [(np.fft.fft(segment)) for segment in self.unfiltered_segments]
        amplitudes = np.mean([np.abs(res) for res in fft_results], axis=0)

        lower_lim = 10
        lim = 4000

        sample_spacing_cm = (self.m_per_sample * 100)
        n = len(self.mean_segment)

        frequencies = np.fft.fftfreq(n, d=sample_spacing_cm)
        positive_frequencies = frequencies[:n // 2]

        ax.plot(positive_frequencies[lower_lim:lim], amplitudes[lower_lim:lim])
        ax.set_ylabel("Amplitude [{}]".format(self.unit))
        ax.set_xlabel("Frequency [1/cm]")

        # Add an upper axis for wavelength
        ax2 = ax.twiny()

        def freq_to_wavelength(freq):
            return np.where(freq != 0, 1.0 / freq, np.inf)

        ax2.set_xlim(ax.get_xlim())
        upper_ticks = ax.get_xticks()

        upper_tick_labels = [f"{freq_to_wavelength(x):.2f}" if x != 0 else '∞' for x in upper_ticks]

        ax2.set_xticklabels(upper_tick_labels)  # Set the wavelength labels
        ax2.set_xlabel("Wavelength [cm]")

        peaks, _ = find_peaks(amplitudes[0:lim], distance=10, prominence=100)
        ax.scatter(positive_frequencies[peaks], amplitudes[peaks], color='red')

        plt.tight_layout()
        return cd_profile_fig, colormap_fig, cd_spectrum_fig


if __name__ == "__main__":
    loader = DataLoader('Pm147-test_20230612.txt', tape_channel="Caliper")
    # x Caliper Gloss 1 Transmission Gloss 2 Basis Weight 1 Basis Weight 2 Ash (abs)     R0
    # loader.plot_data_cd("Basis Weight 1")
    loader.formation()
    plt.show()
