from pylatex import Document, Package, Section, Figure, MiniPage, NoEscape, Tabular, Itemize
import matplotlib.pyplot as plt
import matplotlib
from loader import DataLoader
from settings import DEBUG

matplotlib.use('Agg')

channels = ["Basis Weight 1", "Caliper", "Transmission", "Gloss 1", "Gloss 2", "Basis Weight 2", "Ash (abs)", "R0"]

customer = "Example report customer"
grade = "Board"
grammage = 45.50
d = DataLoader('Pm147-test_20230612.txt', tape_channel="Caliper")
measured_bw_mean = d.get_mean("Basis Weight 1")
num_samples = len(d.segments)



def main(fname):
    doc = Document(fname)

    # Set font to Helvetica (similar to Arial)
    doc.preamble.append(Package('fontenc', options=['T1']))
    doc.preamble.append(Package('helvet'))
    doc.preamble.append(NoEscape(r'\renewcommand{\familydefault}{\sfdefault}'))
    doc.preamble.append(NoEscape(r'\usepackage{siunitx}'))

    # Include hyperref for links in the table of contents
    doc.preamble.append(Package('hyperref'))

    # Header configuration to include logo on all pages
    doc.preamble.append(NoEscape(r'\usepackage{fancyhdr}'))
    doc.preamble.append(NoEscape(r'\pagestyle{fancy}'))
    doc.preamble.append(NoEscape(r'\fancyhf{}'))  # Clear default headers and footers

    doc.preamble.append(NoEscape(r'\lhead{\includegraphics[width=3cm]{img/logo.png}}'))  # Logo in the left header
    doc.preamble.append(
        NoEscape(r'\rhead{\Large\textbf{Tapio Measurement Technologies Oy}\\\normalsize{Analysis services}}')
    )  # Title in the right header

    # Set geometry package options
    doc.packages.append(Package('geometry', options=['left=2cm', 'right=2cm', 'top=3cm', 'headheight=2cm']))

    doc.preamble.append(
        NoEscape(r'\newcommand{\customcaption}[1]{'
                 r'\captionsetup{labelformat=empty}'
                 r'\caption{#1}}'))

    # Table of Contents

    doc.append(NoEscape(r'\section*{Cross Direction Measurement Report}'))
    # Creating a table
    with doc.create(Tabular('ll')) as table:  # 'll' specifies two left-aligned columns
        table.add_row(('Date:', NoEscape('\\today')))
        table.add_row(('Customer:', customer))
        table.add_row(('Grade:', grade))
        table.add_row(('Grammage:', NoEscape(r"{:.2f} g/m²".format(grammage))))
        # table.add_row(('Grammage:', NoEscape(r"{:.2f} $\mathrm{{\frac{{g}}{{m^2}}}}$".format(grammage))))
        table.add_row(('Measured basis weight mean:', r"{:.2f} g/m²".format(measured_bw_mean)))

    doc.append(NoEscape(r'\section*{Measurement procedure}'))
    doc.append(
        NoEscape(
            r"{} cross direction (CD) sample strips were measured with a Tapio PMA Paper Machine Analyzer at Tapio Measurement Technologies laboratory.\\"
            .format(num_samples)))

    # Start of the minipage environment for side-by-side content
    with doc.create(MiniPage(width="0.5\\textwidth")) as left_minipage:
        left_minipage.append(NoEscape(r'\subsubsection*{Sampling}'))
        # Content for the left column
        left_minipage.append(NoEscape(r'\includegraphics[width=6cm]{img/cd.pdf}'))
        left_minipage.append(
            NoEscape(r'\\Number of CD sample strips N = {}\\Sampling resolution d = 0.8 mm'.format(num_samples)))

    with doc.create(MiniPage(width="0.5\\textwidth")) as right_minipage:
        # Content for the right column
        right_minipage.append(NoEscape(r'\vspace{-2em}\subsubsection*{Measured variables}'))
        with right_minipage.create(Tabular('ll')) as table:
            table.add_row((NoEscape(r'\textbf{Variable}'), NoEscape(r'\textbf{Unit}')))
            for channel in channels:
                table.add_row((channel, d.get_unit(channel)))

    doc.append(NoEscape(r'\tableofcontents'))
    doc.append(NoEscape(r'\newpage'))
    with doc.create(Section("Tapio Laboratory Analysis Service", numbering=True)):

        with doc.create(Itemize()) as itemize:
            itemize.add_item("Tapio Laboratory Analysis service provides the customer an in-depth measurement of all paper and board grades using a Tapio PMA analyzer.")
            itemize.add_item("Customer sends samples to Tapio laboratory for measurement. MD rolls and CD sample strips can be measured.")
            itemize.add_item("A detailed report is provided, with an additional online meeting to discuss the findings with Tapio experts.")
            itemize.add_item("The analysis is oriented in problem-solving and specializes in troubleshooting and finding the root causes of variations in paper.")
            itemize.add_item("Swift measurement of samples after reception at Tapio Laboratory.")
            itemize.add_item("Contact info@tapiotechnologies.com for more information.")


    doc.append(NoEscape(r'\newpage'))

    def create_section(channel):
        stats = d.get_stats(channel)
        vca_stats = d.get_vca_stats(channel)

        with doc.create(Section(channel, numbering=True)):
            doc.append(NoEscape(r'\subsection*{' + channel + r' CD Profile}'))

            cd_profile_fig, colormap_fig, cd_spectrum_fig = d.plot_data_cd(channel)

            plt.figure(cd_profile_fig.number)
            with doc.create(Figure(position='htbp')) as plot:
                plot.add_plot(width=NoEscape(r'1\textwidth'), dpi=300)
                # plot.add_caption('CD Profile')

            doc.append(NoEscape(r'\subsection*{' + channel + ' Statistics}'))
            with doc.create(MiniPage(width=NoEscape(r'0.5\textwidth'))) as minipage1:
                minipage1.append(NoEscape(r'\subsubsection*{Mean profile}'))
                with minipage1.create(Tabular('lrr')) as table1:
                    table1.add_row(("", d.get_unit(channel), r"% of mean"))
                    table1.add_row(("Mean", "{:.2f}".format(stats['mean']), "{:.2f}".format(stats['mean_p'])))
                    table1.add_row(("Min", "{:.2f}".format(stats['min']), "{:.2f}".format(stats['min_p'])))
                    table1.add_row(("Max", "{:.2f}".format(stats['max']), "{:.2f}".format(stats['max_p'])))
                    table1.add_row(("Peak-to-peak", "{:.2f}".format(stats['pp']), "{:.2f}".format(stats['pp_p'])))
                    table1.add_row(("Standard deviation", "{:.2f}".format(stats['std_dev']), "{:.2f}".format(stats['std_dev_p'])))
                    # Add more rows to the first table as needed

            # Add some horizontal space between the tables (optional)
            # doc.append(NoEscape(r'\hspace{60mm}'))

            with doc.create(MiniPage(width=NoEscape(r'0.5\textwidth'))) as minipage2:
                minipage2.append(NoEscape(r'\subsubsection*{Mean profile 10\% of ends removed}'))
                with minipage2.create(Tabular('lrr')) as table2:
                    table2.add_row(("", d.get_unit(channel), r"% of mean"))
                    table2.add_row(("Mean", "{:.2f}".format(stats['le_mean']), "{:.2f}".format(stats['le_mean_p'])))
                    table2.add_row(("Min", "{:.2f}".format(stats['le_min']), "{:.2f}".format(stats['le_min_p'])))
                    table2.add_row(("Max", "{:.2f}".format(stats['le_max']), "{:.2f}".format(stats['le_max_p'])))
                    table2.add_row(("Peak-to-peak", "{:.2f}".format(stats['le_pp']), "{:.2f}".format(stats['le_pp_p'])))
                    table2.add_row(("Standard deviation", "{:.2f}".format(stats['le_std_dev']), "{:.2f}".format(stats['le_std_dev_p'])))

            doc.append(NoEscape(r'\newpage'))
            doc.append(NoEscape(r'\subsection*{' + channel + ' Variance Component Analysis}'))

            with doc.create(MiniPage(width=NoEscape(r'0.5\textwidth'))) as minipage1:
                minipage1.append(NoEscape(r'\subsubsection*{Mean profile}'))
                with minipage1.create(Tabular('lrr')) as table1:
                    table1.add_row(("", d.get_unit(channel), r"% of mean"))
                    table1.add_row(("Total standard deviation", "{:.2f}".format(vca_stats['total_std_dev']), "{:.2f}".format(vca_stats['total_std_dev_p'])))
                    table1.add_row(("MD standard deviation", "{:.2f}".format(vca_stats['md_std_dev']), "{:.2f}".format(vca_stats['md_std_dev_p'])))
                    table1.add_row(("CD standard deviation", "{:.2f}".format(vca_stats['cd_std_dev']), "{:.2f}".format(vca_stats['cd_std_dev_p'])))
                    table1.add_row(("Residual standard deviation", "{:.2f}".format(vca_stats['residual_std_dev']), "{:.2f}".format(vca_stats['residual_std_dev_p'])))


            with doc.create(MiniPage(width=NoEscape(r'0.5\textwidth'))) as minipage2:
                minipage2.append(NoEscape(r'\subsubsection*{Mean profile 10\% of ends removed}'))
                with minipage2.create(Tabular('lrr')) as table2:
                    table2.add_row(("", d.get_unit(channel), r"% of mean"))
                    table2.add_row(("Total standard deviation", "{:.2f}".format(vca_stats['le_total_std_dev']), "{:.2f}".format(vca_stats['le_total_std_dev_p'])))
                    table2.add_row(("MD standard deviation", "{:.2f}".format(vca_stats['le_md_std_dev']), "{:.2f}".format(vca_stats['le_md_std_dev_p'])))
                    table2.add_row(("CD standard deviation", "{:.2f}".format(vca_stats['le_cd_std_dev']), "{:.2f}".format(vca_stats['le_cd_std_dev_p'])))
                    table2.add_row(("Residual standard deviation", "{:.2f}".format(vca_stats['le_residual_std_dev']), "{:.2f}".format(vca_stats['le_residual_std_dev_p'])))



            # doc.append(NoEscape(u"\hspace{-3em}"))
            plt.figure(colormap_fig.number)
            with doc.create(Figure(position='htbp')) as plot:
                plot.add_plot(width=NoEscape(r'1\textwidth'), dpi=300)
                # plot.add_caption('Variance')

            with doc.create(Tabular('ll')) as table:  # 'll' specifies two left-aligned columns
                table.add_row("", "")

            doc.append(NoEscape(r'\newpage'))
            doc.append(NoEscape(r'\subsection*{' + channel + ' CD Spectrum}'))
            plt.figure(cd_spectrum_fig.number)
            with doc.create(Figure(position='htbp')) as plot:
                plot.add_plot(width=NoEscape(r'1\textwidth'), dpi=300)
                # plot.add_caption('Variance')

            doc.append(NoEscape(r'\subsection*{Significant frequencies in ' + channel + r' CD Spectrum}'))

            with doc.create(Tabular('lrr')) as table:  # 'll' specifies two left-aligned columns
                table.add_row("Frequency (1/m)", "Wavelength (m)", "Amplitude")

            doc.append(NoEscape(r'\newpage'))

    if DEBUG:
        create_section("Basis Weight 1")
    else:
        for channel in channels:
            create_section(channel)

    doc.generate_pdf()


if __name__ == '__main__':

    main('tapio-report')
