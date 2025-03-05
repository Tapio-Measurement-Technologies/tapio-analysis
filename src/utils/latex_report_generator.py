from pylatex import Document as LatexDocument, Section, Subsection, Figure, NoEscape, Package, Table, Tabular
import os
import shutil
import numpy as np
import io
import uuid
from .report_generator import ReportGenerator
import settings


class LatexReportGenerator(ReportGenerator):
    def generate(self, output_path):
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_path) or '.'
        images_dir = os.path.join(output_dir, 'images')
        os.makedirs(images_dir, exist_ok=True)

        # Create document
        doc = LatexDocument(documentclass='article')

        # Set font to Helvetica (similar to Arial)
        doc.preamble.append(Package('fontenc', options=['T1']))
        doc.preamble.append(Package('helvet'))
        doc.preamble.append(
            NoEscape(r'\renewcommand{\familydefault}{\sfdefault}'))
        doc.preamble.append(Package('siunitx'))

        # Include hyperref for links in the table of contents
        doc.preamble.append(Package('hyperref', options=['hidelinks']))

        # Header configuration to include logo on all pages
        doc.preamble.append(Package('fancyhdr'))
        doc.preamble.append(NoEscape(r'\pagestyle{fancy}'))
        doc.preamble.append(NoEscape(r'\fancyhf{}'))

        # Copy header image to images directory if it exists
        if self.header_image_path:
            header_image_name = self._copy_and_convert_image(
                self.header_image_path, images_dir, 'header_logo')
            if header_image_name:
                # Logo in the left header
                doc.preamble.append(NoEscape(
                    r'\lhead{\includegraphics[width=3cm]{images/' + header_image_name + r'}}'))

        # Right header with title and subtitle
        doc.preamble.append(NoEscape(
            r'\rhead{\Large\textbf{' + self.report_title + r'}\\\normalsize{' + self.report_subtitle + r'}}'))

        # Set geometry package options
        doc.packages.append(Package('geometry', options=[
                            'left=2cm', 'right=2cm', 'top=3cm', 'headheight=2cm']))

        # Set graphics path
        doc.preamble.append(NoEscape(r'\graphicspath{{./images/}}'))

        # Add title section
        doc.append(NoEscape(r'\section*{' + self.report_title + r'}'))

        # Add info table
        with doc.create(Tabular('ll')) as table:
            table.add_row(('Date:', '\\today'))
            if self.additional_info:
                for line in self.additional_info.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        table.add_row((key.strip() + ':', value.strip()))

        # Add measurement procedure section
        doc.append(NoEscape(r'\newpage'))  # Force new page
        doc.append(NoEscape(r'\section*{Measurement procedure}'))

        # Create a minipage environment for text and image side by side
        doc.append(NoEscape(r'\begin{minipage}[t]{0.6\textwidth}'))
        doc.append(
            NoEscape(
                r"{} cross direction (CD) sample strips were measured with a Tapio Analyzer at the Tapio Measurement Technologies laboratory.\\"
                .format(5)))
        doc.append(NoEscape(r'\end{minipage}'))
        
        # Add sample image if it exists
        if self.sample_image_path:
            sample_image_name = self._copy_and_convert_image(
                self.sample_image_path, images_dir, 'sample_image')
            if sample_image_name:
                doc.append(NoEscape(r'\hfill'))  # Push image to the right
                doc.append(NoEscape(r'\begin{minipage}[t]{0.35\textwidth}'))
                doc.append(NoEscape(
                    r'\includegraphics[width=\textwidth]{images/' + sample_image_name + r'}'))
                doc.append(NoEscape(r'\end{minipage}'))

        # Add table of contents
        doc.append(NoEscape(r'\tableofcontents'))
        doc.append(NoEscape(r'\newpage'))

        # Add sections
        for section in self.sections:
            self._add_section_to_latex(doc, section, images_dir)

        # Generate PDF
        if settings.REPORT_GENERATE_PDF:
            try:
                doc.generate_pdf(os.path.splitext(
                    output_path)[0], clean_tex=False)
            except Exception as e:
                # If PDF generation fails, at least save the .tex file
                doc.generate_tex(os.path.splitext(output_path)[0])
                raise Exception(
                    f"Failed to generate PDF. LaTeX file saved. Error: {str(e)}")
        else:
            doc.generate_tex(os.path.splitext(output_path)[0])

    def _add_section_to_latex(self, doc, section, images_dir):
        with doc.create(Section(section.section_name, numbering=True)):
            for analysis in section.analysis_widgets:
                if settings.REPORT_ENABLE_ANALYSIS_TITLE:
                    analysis_title = analysis.analysis_title or f"{analysis.analysis_name} {analysis.get_channel_text()}"
                    with doc.create(Subsection(analysis_title)):
                        self._add_analysis_to_latex(doc, analysis, images_dir)
                else:
                    self._add_analysis_to_latex(doc, analysis, images_dir)

    def _add_analysis_to_latex(self, doc, analysis, images_dir):
        # Add info string if it exists
        if analysis.info_string:
            doc.append(
                NoEscape(r'\textit{' + analysis.info_string + r'}\par\vspace{0.5em}'))

        # Generate unique identifier for this analysis
        analysis_id = str(uuid.uuid4())[:8]

        # Add plot image
        plot_filename = f"plot_{analysis.analysis_name.lower().replace(' ', '_')}_{analysis_id}"
        with doc.create(Figure(position='htbp')) as fig:
            # Save plot image
            plot_img = self._save_plot_image(analysis.controller.getPlotImage(
                format="pdf"), images_dir, plot_filename, format="pdf")
            if plot_img:
                fig.add_image(plot_filename, width=NoEscape('1\\textwidth'))

        # Add stats table
        data = analysis.controller.getStatsTableData()
        if data:
            # Get number of columns
            shape = np.shape(data)
            num_cols = shape[1] if len(shape) > 1 else 1

            # Create table with booktabs style
            with doc.create(Table(position='htbp')) as table:
                # Create tabular environment with column specifications
                col_spec = '|' + \
                    '|'.join(
                        ['l' if i == 0 else 'r' for i in range(num_cols)]) + '|'
                tabular = Tabular(col_spec)
                table.append(NoEscape(r'\centering'))
                table.append(tabular)

                # Add the data
                tabular.add_hline()
                for row_data in data:
                    # Convert all data to strings and escape special characters
                    escaped_row = []
                    for i, cell in enumerate(row_data):
                        cell_str = str(cell).strip()
                        # Try to format numbers with siunitx if it's a number
                        try:
                            float(cell_str)  # Check if it's a number
                            escaped_row.append(
                                NoEscape(rf'\num{{{cell_str}}}'))
                        except ValueError:
                            escaped_row.append(cell_str)

                    tabular.add_row(escaped_row)
                    tabular.add_hline()

            # Add vertical space after the table
            doc.append(NoEscape(r'\vspace{1em}'))

        # Add new page after each analysis
        doc.append(NoEscape(r'\newpage'))

    def _copy_and_convert_image(self, src_path, dest_dir, name):
        """Copy image to destination directory and return the new filename"""
        if not src_path or not os.path.exists(src_path):
            return None

        # Get file extension and create new filename
        _, ext = os.path.splitext(src_path)
        new_filename = f"{name}{ext}"
        dest_path = os.path.join(dest_dir, new_filename)

        # Copy file
        shutil.copy2(src_path, dest_path)
        return name  # Return basename without extension for LaTeX

    def _save_plot_image(self, buffer, dest_dir, name, format="png"):
        """Save plot from BytesIO buffer to destination directory"""
        if not buffer or not isinstance(buffer, io.BytesIO):
            return None

        # Save as PNG
        dest_path = os.path.join(dest_dir, f"{name}.{format}")

        # Write buffer contents to file
        with open(dest_path, 'wb') as f:
            f.write(buffer.getvalue())

        return name  # Return basename without extension for LaTeX
