__all__ = ["FittingResultViewer"]

import copy
import logging
import pickle
import time
import typing
from collections import Counter

import numpy as np
import qtawesome as qta
from PySide2.QtCore import Qt
from PySide2.QtGui import QCursor, QFont
from PySide2.QtWidgets import (QAbstractItemView, QComboBox, QDialog,
                               QFileDialog, QGridLayout, QLabel, QMenu,
                               QMessageBox, QPushButton, QTableWidget,
                               QTableWidgetItem)
from QGrain.algorithms import DistributionType
from QGrain.algorithms.AsyncFittingWorker import AsyncFittingWorker
from QGrain.algorithms.distributions import get_distance_func_by_name
from QGrain.algorithms.moments import logarithmic
from QGrain.charts.BoxplotChart import BoxplotChart
from QGrain.charts.DistanceCurveChart import DistanceCurveChart
from QGrain.charts.MixedDistributionChart import MixedDistributionChart
from QGrain.models.ClassicResolverSetting import built_in_distances
from QGrain.models.FittingResult import FittingResult
from QGrain.models.GrainSizeSample import GrainSizeSample
from QGrain.models.FittingTask import FittingTask

class FittingResultViewer(QDialog):
    PAGE_ROWS = 20
    logger = logging.getLogger("root.QGrain.ui.FittingResultViewer")
    def __init__(self, parent=None):
        flags = Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint
        super().__init__(parent=parent, f=flags)
        self.setWindowTitle(self.tr("SSU Fitting Result Viewer"))
        self.__fitting_results = []
        self.__reference_map = {}
        self.retry_tasks = {}
        self.init_ui()
        self.boxplot_chart = BoxplotChart(parent=self, toolbar=True)
        self.distance_chart = DistanceCurveChart(parent=self, toolbar=True)
        self.mixed_distribution_chart = MixedDistributionChart(parent=self, toolbar=True, use_animation=True)
        self.file_dialog = QFileDialog(parent=self)
        self.async_worker = AsyncFittingWorker()
        self.async_worker.background_worker.task_succeeded.connect(self.on_fitting_succeeded)
        self.async_worker.background_worker.task_failed.connect(self.on_fitting_failed)
        self.update_page_list()
        self.update_page(self.page_index)
        self.msg_box = QMessageBox(self)
        self.msg_box.setWindowFlags(Qt.Drawer)

        self.outlier_msg_box = QMessageBox(self)
        self.outlier_msg_box.setWindowFlags(Qt.Drawer)
        self.outlier_msg_box.setStandardButtons(QMessageBox.Discard|QMessageBox.Retry|QMessageBox.Ignore)


    def init_ui(self):
        self.setWindowTitle(self.tr("Fitting Result Viewer"))
        self.data_table = QTableWidget(100, 100)
        self.data_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.data_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.main_layout = QGridLayout(self)
        self.main_layout.addWidget(self.data_table, 0, 0, 1, 3)

        self.previous_button = QPushButton(qta.icon("mdi.skip-previous-circle"), self.tr("Previous"))
        self.previous_button.setToolTip(self.tr("Click to back to the previous page."))
        self.previous_button.clicked.connect(self.on_previous_button_clicked)
        self.current_page_combo_box = QComboBox()
        self.current_page_combo_box.addItem(self.tr("Page {0}").format(1))
        self.current_page_combo_box.currentIndexChanged.connect(self.update_page)
        self.next_button = QPushButton(qta.icon("mdi.skip-next-circle"), self.tr("Next"))
        self.next_button.setToolTip(self.tr("Click to jump to the next page."))
        self.next_button.clicked.connect(self.on_next_button_clicked)
        self.main_layout.addWidget(self.previous_button, 1, 0)
        self.main_layout.addWidget(self.current_page_combo_box, 1, 1)
        self.main_layout.addWidget(self.next_button, 1, 2)

        self.distance_label = QLabel(self.tr("Distance"))
        self.distance_label.setToolTip(self.tr("It's the function to calculate the difference (on the contrary, similarity) between two samples."))
        self.distance_combo_box = QComboBox()
        self.distance_combo_box.addItems(built_in_distances)
        self.distance_combo_box.setCurrentText("log10MSE")
        self.distance_combo_box.currentTextChanged.connect(lambda: self.update_page(self.page_index))
        self.main_layout.addWidget(self.distance_label, 2, 0)
        self.main_layout.addWidget(self.distance_combo_box, 2, 1, 1, 2)
        self.menu = QMenu(self.data_table)
        self.mark_action = self.menu.addAction(qta.icon("mdi.marker-check"), self.tr("Mark Selection(s) as Reference"))
        self.mark_action.triggered.connect(self.mark_selections)
        self.unmark_action = self.menu.addAction(qta.icon("mdi.do-not-disturb"), self.tr("Unmark Selection(s)"))
        self.unmark_action.triggered.connect(self.unmark_selections)
        self.remove_action = self.menu.addAction(qta.icon("fa.remove"), self.tr("Remove Selection(s)"))
        self.remove_action.triggered.connect(self.remove_selections)
        self.plot_loss_chart_action = self.menu.addAction(qta.icon("mdi.chart-timeline-variant"), self.tr("Plot Loss Chart"))
        self.plot_loss_chart_action.triggered.connect(self.show_distance)
        self.plot_distribution_chart_action = self.menu.addAction(qta.icon("fa5s.chart-area"), self.tr("Plot Distribution Chart"))
        self.plot_distribution_chart_action.triggered.connect(self.show_distribution)
        self.plot_distribution_animation_action = self.menu.addAction(qta.icon("fa5s.chart-area"), self.tr("Plot Distribution Chart (Animation)"))
        self.plot_distribution_animation_action.triggered.connect(self.show_history_distribution)
        self.do_outlier_detection_action = self.menu.addAction(qta.icon("fa5s.chart-area"), self.tr("Do Outlier Detection"))
        self.do_outlier_detection_action.triggered.connect(self.do_outlier_detection)
        self.do_summary_action = self.menu.addAction(qta.icon("fa5s.chart-area"), self.tr("Do Summary"))
        self.do_summary_action.triggered.connect(self.do_summary)
        self.load_dump_action = self.menu.addAction(qta.icon("fa.database"), self.tr("Load Binary Dump"))
        self.load_dump_action.triggered.connect(self.load_dump)
        self.save_dump_action = self.menu.addAction(qta.icon("fa.save"), self.tr("Save Binary Dump"))
        self.save_dump_action.triggered.connect(self.save_dump)
        self.save_excel_action = self.menu.addAction(qta.icon("mdi.microsoft-excel"), self.tr("Save Excel"))
        self.save_excel_action.triggered.connect(self.save_excel)
        self.data_table.customContextMenuRequested.connect(self.show_menu)

    def show_menu(self, pos):
        self.menu.popup(QCursor.pos())

    def show_message(self, title: str, message: str):
        self.msg_box.setWindowTitle(title)
        self.msg_box.setText(message)
        self.msg_box.exec_()

    def show_info(self, message: str):
        self.show_message(self.tr("Info"), message)

    def show_warning(self, message: str):
        self.show_message(self.tr("Warning"), message)

    def show_error(self, message: str):
        self.show_message(self.tr("Error"), message)

    @property
    def distance_name(self) -> str:
        return self.distance_combo_box.currentText()

    @property
    def distance_func(self) -> typing.Callable:
        return get_distance_func_by_name(self.distance_combo_box.currentText())

    @property
    def is_geometric(self) -> bool:
        return self.animation_repeat_checkbox.isChecked()

    @property
    def use_FW57(self) -> bool:
        return self.FW57_checkbox.isChecked()

    @property
    def page_index(self) -> int:
        return self.current_page_combo_box.currentIndex()

    @property
    def n_pages(self) -> int:
        return self.current_page_combo_box.count()

    @property
    def n_results(self) -> int:
        return len(self.__fitting_results)

    @property
    def unit(self) -> str:
        return "μm" if self.is_geometric else "φ"

    @property
    def selections(self):
        start = self.page_index*self.PAGE_ROWS
        temp = set()
        for item in self.data_table.selectedRanges():
            for i in range(item.topRow(), min(self.PAGE_ROWS+1, item.bottomRow()+1)):
                temp.add(i+start)
        indexes = list(temp)
        indexes.sort()
        return indexes

    def update_page_list(self):
        last_page_index = self.page_index
        if self.n_results == 0:
            n_pages = 1
        else:
            n_pages, left = divmod(self.n_results, self.PAGE_ROWS)
            if left != 0:
                n_pages += 1
        self.current_page_combo_box.blockSignals(True)
        self.current_page_combo_box.clear()
        self.current_page_combo_box.addItems([self.tr("Page {0}").format(i+1) for i in range(n_pages)])
        if last_page_index >= n_pages:
            self.current_page_combo_box.setCurrentIndex(n_pages-1)
        else:
            self.current_page_combo_box.setCurrentIndex(last_page_index)
        self.current_page_combo_box.blockSignals(False)

    def update_page(self, page_index: int):
        def write(row: int, col: int, value: str):
            if isinstance(value, str):
                pass
            elif isinstance(value, int):
                value = str(value)
            elif isinstance(value, float):
                value = f"{value: 0.4f}"
            else:
                value = value.__str__()
            item = QTableWidgetItem(value)
            item.setTextAlignment(Qt.AlignCenter)
            self.data_table.setItem(row, col, item)
        # necessary to clear
        self.data_table.clear()
        if page_index == self.n_pages - 1:
            start = page_index * self.PAGE_ROWS
            end = self.n_results
        else:
            start, end = page_index * self.PAGE_ROWS, (page_index+1) * self.PAGE_ROWS
        self.data_table.setRowCount(end-start)
        self.data_table.setColumnCount(8)
        self.data_table.setHorizontalHeaderLabels([
            self.tr("Resolver"),
            self.tr("Distribution Type"),
            self.tr("N_components"),
            self.tr("N_iterations"),
            self.tr("Spent Time [s]"),
            self.tr("Final Distance"),
            self.tr("Has Reference"),
            self.tr("Is Reference")])
        sample_names = [result.sample.name for result in self.__fitting_results[start: end]]
        self.data_table.setVerticalHeaderLabels(sample_names)
        for row, result in enumerate(self.__fitting_results[start: end]):
            write(row, 0, result.task.resolver)
            write(row, 1, self.get_distribution_name(result.task.distribution_type))
            write(row, 2, result.task.n_components)
            write(row, 3, result.n_iterations)
            write(row, 4, result.time_spent)
            write(row, 5, self.distance_func(result.sample.distribution, result.distribution))
            has_ref = result.task.initial_guess is not None or result.task.reference is not None
            write(row, 6, self.tr("Yes") if has_ref else self.tr("No"))
            is_ref = result.uuid in self.__reference_map
            write(row, 7, self.tr("Yes") if is_ref else self.tr("No"))

        self.data_table.resizeColumnsToContents()

    def on_previous_button_clicked(self):
        if self.page_index > 0:
            self.current_page_combo_box.setCurrentIndex(self.page_index-1)

    def on_next_button_clicked(self):
        if self.page_index < self.n_pages - 1:
            self.current_page_combo_box.setCurrentIndex(self.page_index+1)

    def get_distribution_name(self, distribution_type: DistributionType):
        if distribution_type == DistributionType.Normal:
            return self.tr("Normal")
        elif distribution_type == DistributionType.Weibull:
            return self.tr("Weibull")
        elif distribution_type == DistributionType.SkewNormal:
            return self.tr("Skew Normal")
        else:
            raise NotImplementedError(distribution_type)

    def add_result(self, result: FittingResult):
        if self.n_results == 0 or \
            (self.page_index == self.n_pages - 1 and \
            divmod(self.n_results, self.PAGE_ROWS)[-1] != 0):
            need_update = True
        else:
            need_update = False
        self.__fitting_results.append(result)
        self.update_page_list()
        if need_update:
            self.update_page(self.page_index)

    def add_results(self, results: typing.List[FittingResult]):
        if self.n_results == 0 or \
            (self.page_index == self.n_pages - 1 and \
            divmod(self.n_results, self.PAGE_ROWS)[-1] != 0):
            need_update = True
        else:
            need_update = False
        self.__fitting_results.extend(results)
        self.update_page_list()
        if need_update:
            self.update_page(self.page_index)

    def mark_results(self, results: typing.List[FittingResult]):
        for result in results:
            self.__reference_map[result.uuid] = result

        self.update_page(self.page_index)

    def unmark_results(self, results: typing.List[FittingResult]):
        for result in results:
            if result.uuid in self.__reference_map:
                self.__reference_map.pop(result.uuid)

        self.update_page(self.page_index)

    def mark_selections(self):
        results = [self.__fitting_results[selection] for selection in self.selections]
        self.mark_results(results)

    def unmark_selections(self):
        results = [self.__fitting_results[selection] for selection in self.selections]
        self.unmark_results(results)

    def remove_results(self, indexes):
        results = []
        for i in reversed(indexes):
            res = self.__fitting_results.pop(i)
            results.append(res)
        self.unmark_results(results)
        self.update_page_list()
        self.update_page(self.page_index)

    def remove_selections(self):
        indexes = self.selections
        self.remove_results(indexes)

    def show_distance(self):
        results = [self.__fitting_results[i] for i in self.selections]
        if results is None or len(results) == 0:
            return
        result = results[0]
        self.distance_chart.show_distance_series(
            result.get_distance_series(self.distance_name),
            title=result.sample.name)
        self.distance_chart.show()

    def show_distribution(self):
        results = [self.__fitting_results[i] for i in self.selections]
        if results is None or len(results) == 0:
            return
        result = results[0]
        self.mixed_distribution_chart.show_model(result.view_model)
        self.mixed_distribution_chart.show()

    def show_history_distribution(self):
        results = [self.__fitting_results[i] for i in self.selections]
        if results is None or len(results) == 0:
            return
        result = results[0]
        self.mixed_distribution_chart.show_result(result)
        self.mixed_distribution_chart.show()

    def load_dump(self, mark_ref=False):
        filename, _  = self.file_dialog.getOpenFileName(self, self.tr("Select a binary dump file of SSU results"),
                                            None, self.tr("Binary dump (*.dump)"))
        if filename is None or filename == "":
            return
        with open(filename, "rb") as f:
            results = pickle.load(f)
            valid = True
            if isinstance(results, list):
                for result in results:
                    if not isinstance(result, FittingResult):
                        valid = False
                        break
            else:
                valid = False

            if valid:
                self.add_results(results)
                if mark_ref:
                    self.mark_results(results)
            else:
                self.show_error(self.tr("The binary dump file is invalid."))

    def save_dump(self):
        if self.n_results == 0:
            self.show_warning(self.tr("There is not any result in the list."))
            return
        filename, _  = self.file_dialog.getSaveFileName(self, self.tr("Save the SSU results to binary dump file"),
                                            None, self.tr("Binary dump (*.dump)"))
        if filename is None or filename == "":
            return
        with open(filename, "wb") as f:
            pickle.dump(self.__fitting_results, f)

    def save_excel(self):
        # TODO: ADD SUPPORT
        self.show_error("NOT IMPLEMENTED")

    def find_similar(self, target: GrainSizeSample, ref_results: typing.List[FittingResult]):
        assert len(ref_results) != 0
        # sample_moments = logarithmic(sample.classes_φ, sample.distribution)
        # keys_to_check = ["mean", "std", "skewness", "kurtosis"]

        start_time = time.time()
        from scipy.interpolate import interp1d
        min_distance = 1e100
        min_result = None
        trans_func = interp1d(target.classes_φ, target.distribution, bounds_error=False, fill_value=0.0)
        for result in ref_results:
            # TODO: To scale the classes of result to that of sample
            # use moments to calculate? MOMENTS MAY NOT BE PERFECT, MAY IGNORE THE MINOR DIFFERENCE
            # result_moments = logarithmic(result.classes_φ, result.distribution)
            # distance = sum([(sample_moments[key]-result_moments[key])**2 for key in keys_to_check])
            trans_dist = trans_func(result.classes_φ)
            distance = self.distance_func(result.distribution, trans_dist)

            if distance < min_distance:
                min_distance = distance
                min_result = result

        self.logger.debug(f"It took {time.time()-start_time:0.4f} s to query the reference from {len(ref_results)} results.")
        return min_result

    def query_reference(self, sample: GrainSizeSample):
        if len(self.__reference_map) == 0:
            self.logger.debug("No result is marked as reference.")
            return None
        return self.find_similar(sample, self.__reference_map.values())

    def on_fitting_succeeded(self, result):
        result_replace_index = self.retry_tasks[result.task.uuid]
        self.__fitting_results[result_replace_index] = result

        self.update_page(self.page_index)

    def on_fitting_failed(self, task):
        pass

    def retry_results(self, indexes, results):
        self.retry_tasks = {}
        for index, result in zip(indexes, results):
            query = self.query_reference(result.sample)
            ref_result = None
            if query is None:
                nearby_results = self.__fitting_results[index-5: index]+self.__fitting_results[index+1: index+6]
                ref_result = self.find_similar(result.sample, nearby_results)
            else:
                ref_result = query
            keys = ["mean", "std", "skewness"]
            reference = [{key: comp.logarithmic_moments[key] for key in keys} for comp in ref_result.components]
            task = FittingTask(result.sample,
                               ref_result.distribution_type,
                               ref_result.n_components,
                               resolver=ref_result.task.resolver,
                               resolver_setting=ref_result.task.resolver_setting,
                               reference=reference)
            self.logger.debug(task)
            self.retry_tasks[task.uuid] = index
            self.async_worker.execute_task(task)

    def do_outlier_detection(self):
        if self.n_results == 0:
            self.show_warning(self.tr("There is not any result in the list."))
            return
        elif self.n_results < 10:
            self.show_warning(self.tr("The results in list are too less."))
            return
        distances = []
        for result in self.__fitting_results:
            distances.append(result.get_distance(self.distance_name))
        distances = np.array(distances)
        self.boxplot_chart.show_dataset([distances], xlabels=[self.distance_name], ylabel=self.tr("Distance"))
        self.boxplot_chart.show()

        # calculate the 1/4, 1/2, and 3/4 postion value to judge which result is invalid
        # 1. the mean squared errors are much higher in the results which are lack of components
        # 2. with the component number getting higher, the mean squared error will get lower and finally reach the minimum
        median = np.median(distances)
        upper_group = distances[np.greater(distances, median)]
        lower_group = distances[np.less(distances, median)]
        value_1_4 = np.median(lower_group)
        value_3_4 = np.median(upper_group)
        distance_QR = value_3_4 - value_1_4
        outlier_results = []
        outlier_indexes = []
        for i, (result, distance) in enumerate(zip(self.__fitting_results, distances)):
            if distance > value_3_4 + distance_QR * 1.5:
            # if distance > value_3_4 + distance_QR * 1.5 or distance < value_1_4 - distance_QR * 1.5:
                outlier_results.append(result)
                outlier_indexes.append(i)
        self.logger.debug(f"Outlier results: {[result.sample.name for result in outlier_results]}")
        if len(outlier_results) == 0:
            self.show_info(self.tr("No fitting result was evaluated as an outlier."))
        else:
            self.outlier_msg_box.setText(self.tr("The fitting results of the following samples were evaluated as outliers by Tukey's test:\n    {0}\nHow to deal with them?").format(
                    ", ".join([result.sample.name for result in outlier_results])))
            res = self.outlier_msg_box.exec_()
            if res == QMessageBox.Discard:
                self.remove_results(outlier_indexes)
            elif res == QMessageBox.Retry:
                self.retry_results(outlier_indexes, outlier_results)
            else:
                pass

    def do_summary(self):
        if self.n_results == 0:
            self.show_warning(self.tr("There is not any result in the list."))
            return
        elif self.n_results < 10:
            self.show_warning(self.tr("The results in list are too less."))
            return
        import matplotlib.pyplot as plt
        n_components_list = [result.n_components for result in self.__fitting_results]
        count_dict = Counter(n_components_list)
        self.logger.debug(f"N_components: {count_dict}")
        figure = plt.figure(figsize=(6, 4))
        cmap = plt.get_cmap("tab10")
        axes = figure.add_subplot(1, 1, 1)
        for result in self.__fitting_results:
            for i, comp in enumerate(result.components):
                plt.plot(result.classes_μm, comp.distribution, c=cmap(i))
        axes.set_xscale("log")
        figure.tight_layout()
        figure.show()


if __name__ == "__main__":
    import sys

    from QGrain.entry import setup_app
    app = setup_app()
    main = FittingResultViewer()
    main.show()
    sys.exit(app.exec_())
