import logging
import os
import sys
from typing import *

from PySide6 import QtCore, QtGui, QtWidgets
from qt_material import apply_stylesheet, list_themes

from .. import QGRAIN_ROOT_PATH
from ..models import Dataset
from ..protos.client import QGrainClient
from ..io import save_pca, save_statistics
from . import EXTRA, setup_app, setup_logging
from .About import About
from .ClusteringAnalyzer import ClusteringAnalyzer
from .DatasetGenerator import DatasetGenerator
from .DatasetLoader import DatasetLoader
from .EMMAAnalyzer import EMMAAnalyzer
from .EMMASettings import EMMASettings
from .RuntimeLog import *
from .PCAAnalyzer import PCAAnalyzer
from .ParameterEditor import ParameterEditor
from .SSUAnalyzer import SSUAnalyzer
from .SSUMulticoreAnalyzer import SSUMulticoreAnalyzer
from .SSUSettings import SSUSettings
from .StatisticalAnalyzer import StatisticalAnalyzer
from .UDMAnalyzer import UDMAnalyzer
from .UDMSettings import UDMSettings


class MainWindow(QtWidgets.QMainWindow):
    logger = logging.getLogger("QGrain.MainWindow")

    def __init__(self):
        super().__init__()
        self._dataset: Optional[Dataset] = None
        self._translator: Optional[QtCore.QTranslator] = None
        self._client = QGrainClient()
        self.setWindowTitle("QGrain")
        self.ssu_setting_dialog = SSUSettings(self)
        self.emma_setting_dialog = EMMASettings(parent=self, client=self._client)
        self.udm_setting_dialog = UDMSettings(parent=self, client=self._client)
        self.parameter_editor = ParameterEditor(self)
        self.ssu_multicore_analyzer = SSUMulticoreAnalyzer(self)
        self.tab_widget = QtWidgets.QTabWidget(self)
        self.tab_widget.setTabPosition(QtWidgets.QTabWidget.West)
        self.setCentralWidget(self.tab_widget)
        self.dataset_generator = DatasetGenerator()
        self.tab_widget.addTab(self.dataset_generator, self.tr("Generator"))
        self.dataset_viewer = StatisticalAnalyzer()
        self.tab_widget.addTab(self.dataset_viewer, self.tr("Statistics"))
        self.pca_analyzer = PCAAnalyzer()
        self.tab_widget.addTab(self.pca_analyzer, self.tr("PCA"))
        self.clustering_analyzer = ClusteringAnalyzer()
        self.tab_widget.addTab(self.clustering_analyzer, self.tr("Clustering"))
        self.ssu_analyzer = SSUAnalyzer(self.ssu_setting_dialog, self.parameter_editor)
        self.tab_widget.addTab(self.ssu_analyzer, self.tr("SSU"))
        self.emma_analyzer = EMMAAnalyzer(self.emma_setting_dialog, self.parameter_editor, client=self._client)
        self.tab_widget.addTab(self.emma_analyzer, self.tr("EMMA"))
        self.udm_analyzer = UDMAnalyzer(self.udm_setting_dialog, self.parameter_editor, client=self._client)
        self.tab_widget.addTab(self.udm_analyzer, self.tr("UDM"))

        # Open
        self.open_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Open"))
        self.open_dataset_action: QtGui.QAction = self.open_menu.addAction(self.tr("Grain Size Dataset"))
        self.open_dataset_action.triggered.connect(lambda: self.load_dataset_dialog.show())
        self.load_ssu_result_action: QtGui.QAction = self.open_menu.addAction(self.tr("SSU Results"))
        self.load_ssu_result_action.triggered.connect(self.ssu_analyzer.result_view.load_results)
        self.load_emma_result_action: QtGui.QAction = self.open_menu.addAction(self.tr("EMMA Result"))
        self.load_emma_result_action.triggered.connect(self.emma_analyzer.load_result)
        self.load_udm_result_action: QtGui.QAction = self.open_menu.addAction(self.tr("UDM Result"))
        self.load_udm_result_action.triggered.connect(self.udm_analyzer.load_result)

        # Save
        self.save_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Save"))
        self.save_statistics_action: QtGui.QAction = self.save_menu.addAction(self.tr("Statistical Result"))
        self.save_statistics_action.triggered.connect(self.on_save_statistics_clicked)
        self.save_pca_action: QtGui.QAction = self.save_menu.addAction(self.tr("PCA Result"))
        self.save_pca_action.triggered.connect(self.on_save_pca_clicked)
        self.save_clustering_action: QtGui.QAction = self.save_menu.addAction(self.tr("Clustering Result"))
        self.save_clustering_action.triggered.connect(self.clustering_analyzer.save_result)
        self.save_ssu_result_action: QtGui.QAction = self.save_menu.addAction(self.tr("SSU Results"))
        self.save_ssu_result_action.triggered.connect(self.ssu_analyzer.result_view.save_results)
        self.save_emma_result_action: QtGui.QAction = self.save_menu.addAction(self.tr("EMMA Result"))
        self.save_emma_result_action.triggered.connect(self.emma_analyzer.save_selected_result)
        self.save_udm_result_action: QtGui.QAction = self.save_menu.addAction(self.tr("UDM Result"))
        self.save_udm_result_action.triggered.connect(self.udm_analyzer.save_selected_result)

        # Config
        self.config_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Configure"))
        self.config_ssu_action: QtGui.QAction = self.config_menu.addAction(self.tr("SSU Algorithm"))
        self.config_ssu_action.triggered.connect(self.ssu_setting_dialog.show)
        self.config_emma_action: QtGui.QAction = self.config_menu.addAction(self.tr("EMMA Algorithm"))
        self.config_emma_action.triggered.connect(self.emma_setting_dialog.show)
        self.config_udm_action: QtGui.QAction = self.config_menu.addAction(self.tr("UDM Algorithm"))
        self.config_udm_action.triggered.connect(self.udm_setting_dialog.show)

        # Experimental
        self.experimental_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Experimental"))
        self.ssu_fit_all_action: QtGui.QAction = self.experimental_menu.addAction(
            self.tr("Perform SSU For All Samples"))
        self.ssu_fit_all_action.triggered.connect(self.ssu_fit_all_samples)
        self.convert_udm_to_ssu_action: QtGui.QAction = self.experimental_menu.addAction(
            self.tr("Convert UDM Result To SSU Results"))
        self.convert_udm_to_ssu_action.triggered.connect(self.convert_udm_to_ssu)
        self.save_all_ssu_figures_action: QtGui.QAction = self.experimental_menu.addAction(
            self.tr("Save Figures For All SSU Results"))
        self.save_all_ssu_figures_action.triggered.connect(self.save_all_ssu_figure)

        # Language
        self.language_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Language"))
        self.language_group = QtGui.QActionGroup(self.language_menu)
        self.language_group.setExclusive(True)
        self.language_actions: list[QtGui.QAction] = []
        for key, name in self.supported_languages:
            action = self.language_group.addAction(name)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, language=key: self.switch_language(language))
            self.language_menu.addAction(action)
            self.language_actions.append(action)
        self.language_actions[0].setChecked(True)
        # Theme
        self.theme_menu: QtWidgets.QMenu = self.menuBar().addMenu(self.tr("Theme"))
        self.theme_group = QtGui.QActionGroup(self.theme_menu)
        self.theme_group.setExclusive(True)
        self.theme_actions = []
        for theme in list_themes():
            action = self.theme_group.addAction(theme)
            action.setCheckable(True)
            app = QtCore.QCoreApplication.instance()
            invert_secondary = theme.startswith("light")
            action.triggered.connect(lambda checked=False, theme=theme, invert_secondary=invert_secondary: apply_stylesheet(app, theme=theme, invert_secondary=invert_secondary, extra=EXTRA))
            self.theme_menu.addAction(action)
            self.theme_actions.append(action)
            if theme == "light_cyan.xml":
                action.setChecked(True)
        # Log
        self.log_action = QtGui.QAction(self.tr("Log"))
        self.log_action.triggered.connect(lambda: self.log_dialog.show())
        self.menuBar().addAction(self.log_action)
        # About
        self.about_action = QtGui.QAction(self.tr("About"))
        self.about_action.triggered.connect(lambda: self.about_dialog.show())
        self.menuBar().addAction(self.about_action)

        self.ssu_multicore_analyzer.result_finished.connect(self.ssu_analyzer.result_view.add_result)
        self.load_dataset_dialog = DatasetLoader(self)
        self.load_dataset_dialog.dataset_loaded.connect(self.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.dataset_viewer.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.pca_analyzer.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.clustering_analyzer.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.ssu_analyzer.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.emma_analyzer.on_dataset_loaded)
        self.load_dataset_dialog.dataset_loaded.connect(self.udm_analyzer.on_dataset_loaded)
        self.log_dialog = RuntimeLog(self)
        self.about_dialog = About(self)
        self.file_dialog = QtWidgets.QFileDialog(parent=self)
        self.normal_msg = QtWidgets.QMessageBox(self)
        self.close_msg = QtWidgets.QMessageBox(self)
        self.close_msg.setWindowTitle(self.tr("Warning"))
        self.close_msg.setText(self.tr("Closing this window will terminate all running tasks, are you sure to close it?"))
        self.close_msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        self.close_msg.setDefaultButton(QtWidgets.QMessageBox.No)

    @property
    def supported_languages(self) -> List[Tuple[str, str]]:
        languages = [("en", "English"),
                     ("zh_CN", "简体中文")]
        return languages

    @property
    def language(self) -> str:
        for i, language_action in enumerate(self.language_actions):
            if language_action.isChecked():
                key, name = self.supported_languages[i]
                return key

    @property
    def theme(self) -> str:
        for i, theme_action in enumerate(self.theme_actions):
            if theme_action.isChecked():
                theme = list_themes()[i]
                return theme

    def show_message(self, title: str, message: str):
        self.normal_msg.setWindowTitle(title)
        self.normal_msg.setText(message)
        self.normal_msg.exec_()

    def show_info(self, message: str):
        self.show_message(self.tr("Info"), message)

    def show_warning(self, message: str):
        self.show_message(self.tr("Warning"), message)

    def show_error(self, message: str):
        self.show_message(self.tr("Error"), message)

    def on_dataset_loaded(self, dataset: Dataset):
        if dataset is None:
            return
        self._dataset = dataset

    def ssu_fit_all_samples(self):
        tasks = self.ssu_analyzer.get_all_tasks()
        self.ssu_multicore_analyzer.setup_tasks(tasks)
        self.ssu_multicore_analyzer.exec()

    def convert_udm_to_ssu(self):
        if self.udm_analyzer.n_results == 0:
            self.show_error(self.tr("There is no UDM result."))
            return
        udm_result = self.udm_analyzer.selected_result
        assert udm_result is not None
        progress_dialog = QtWidgets.QProgressDialog(
            self.tr("Converting UDM result to SSU results..."), self.tr("Cancel"),
            0, 100, self)
        progress_dialog.setWindowTitle("QGrain")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)

        def callback(progress: float):
            if progress_dialog.wasCanceled():
                raise StopIteration()
            progress_dialog.setValue(int(progress*100))
            QtCore.QCoreApplication.processEvents()
        ssu_results = udm_result.to_ssu_results(callback)
        self.ssu_analyzer.result_view.add_results(ssu_results)

    def save_all_ssu_figure(self):
        if self.ssu_analyzer.result_view.n_results == 0:
            self.logger.error("There is no SSU result.")
            self.show_error(self.tr("There is no SSU result."))
            return
        directory = self.file_dialog.getExistingDirectory(
            self, self.tr("Choose a directory to save the figures for all SSU results"),
            ".", QtWidgets.QFileDialog.ShowDirsOnly)
        if directory is None or directory == "":
            return

        try:
            progress_dialog = QtWidgets.QProgressDialog(
                self.tr("Saving the figures for all SSU results..."), self.tr("Cancel"),
                0, 100, self)
            progress_dialog.setWindowTitle("QGrain")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)

            def callback(progress: float):
                if progress_dialog.wasCanceled():
                    raise StopIteration()
                progress_dialog.setValue(int(progress*100))
                QtCore.QCoreApplication.processEvents()
            all_results = self.ssu_analyzer.result_view.all_results
            for i, result in enumerate(all_results):
                self.ssu_analyzer.result_chart.show_chart(result.view_model)
                image = self.ssu_analyzer.result_chart.grab()
                filename = os.path.join(directory, f"{i}.png")
                image.save(filename)
                callback(i/len(all_results))
            callback(1.0)
        except StopIteration as e:
            self.logger.info("Saving task was canceled.")
            progress_dialog.close()
        except Exception as e:
            progress_dialog.close()
            self.logger.exception("An unknown exception was raised. Please check the logs for more details.")
            self.show_error(self.tr("An unknown exception was raised. Please check the logs for more details."))

    def on_save_statistics_clicked(self):
        if self._dataset is None:
            self.logger.error("Dataset has not been loaded.")
            self.show_error(self.tr("Dataset has not been loaded."))
            return
        filename, _ = self.file_dialog.getSaveFileName(
            self, self.tr("Save statistical result"),
            ".", "Microsoft Excel (*.xlsx)")
        if filename is None or filename == "":
            return
        try:
            progress_dialog = QtWidgets.QProgressDialog(
                self.tr("Saving statistical result..."), self.tr("Cancel"),
                0, 100, self)
            progress_dialog.setWindowTitle("QGrain")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)

            def callback(progress: float):
                if progress_dialog.wasCanceled():
                    raise StopIteration()
                progress_dialog.setValue(int(progress*100))
                QtCore.QCoreApplication.processEvents()
            save_statistics(self._dataset, filename, progress_callback=callback, logger=self.logger)
        except StopIteration as e:
            self.logger.info("Saving task was canceled.")
            progress_dialog.close()
        except Exception as e:
            progress_dialog.close()
            self.logger.exception("An unknown exception was raised. Please check the logs for more details.")
            self.show_error(self.tr("An unknown exception was raised. Please check the logs for more details."))

    def on_save_pca_clicked(self):
        if self._dataset is None:
            self.show_error(self.tr("Dataset has not been loaded."))
            return
        filename, _ = self.file_dialog.getSaveFileName(self, self.tr("Save PCA result"),
                                                       ".", "Microsoft Excel (*.xlsx)")
        if filename is None or filename == "":
            return
        try:
            progress_dialog = QtWidgets.QProgressDialog(
                self.tr("Saving PCA result..."), self.tr("Cancel"),
                0, 100, self)
            progress_dialog.setWindowTitle("QGrain")
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            def callback(progress: float):
                if progress_dialog.wasCanceled():
                    raise StopIteration()
                progress_dialog.setValue(int(progress*100))
                QtCore.QCoreApplication.processEvents()
            save_pca(self._dataset, filename, progress_callback=callback, logger=self.logger)
        except StopIteration as e:
            self.logger.info("Saving task was canceled.")
            progress_dialog.close()
        except Exception as e:
            progress_dialog.close()
            self.logger.exception("An unknown exception was raised. Please check the logs for more details.")
            self.show_error(self.tr("An unknown exception was raised. Please check the logs for more details."))

    def switch_language(self, language: str):
        app = QtWidgets.QApplication.instance()
        if self._translator is not None:
            app.removeTranslator(self._translator)
        translator = QtCore.QTranslator(app)
        translator.load(os.path.join(QGRAIN_ROOT_PATH, "assets", language))
        app.installTranslator(translator)
        self._translator = translator

    def changeEvent(self, event: QtCore.QEvent):
        if event.type() == QtCore.QEvent.LanguageChange:
            self.retranslate()

    def closeEvent(self, event: QtGui.QCloseEvent):
        res = self.close_msg.exec_()
        if res == QtWidgets.QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

    def retranslate(self):
        self.setWindowTitle("QGrain")
        self.close_msg.setWindowTitle(self.tr("Warning"))
        self.close_msg.setText(self.tr("Closing this window will terminate all running tasks, are you sure to close it?"))
        self.open_menu.setTitle((self.tr("Open")))
        self.save_menu.setTitle(self.tr("Save"))
        self.open_dataset_action.setText(self.tr("Grain Size Dataset"))
        self.load_ssu_result_action.setText(self.tr("SSU Results"))
        self.load_emma_result_action.setText(self.tr("EMMA Result"))
        self.load_udm_result_action.setText(self.tr("UDM Result"))
        self.save_statistics_action.setText(self.tr("Statistical Result"))
        self.save_pca_action.setText(self.tr("PCA Result"))
        self.save_clustering_action.setText(self.tr("Clustering Result"))
        self.save_ssu_result_action.setText(self.tr("SSU Results"))
        self.save_emma_result_action.setText(self.tr("EMMA Result"))
        self.save_udm_result_action.setText(self.tr("UDM Result"))
        self.config_menu.setTitle(self.tr("Configure"))
        self.config_ssu_action.setText(self.tr("SSU Algorithm"))
        self.config_emma_action.setText(self.tr("EMMA Algorithm"))
        self.config_udm_action.setText(self.tr("UDM Algorithm"))
        self.experimental_menu.setTitle(self.tr("Experimental"))
        self.ssu_fit_all_action.setText(self.tr("Perform SSU For All Samples"))
        self.convert_udm_to_ssu_action.setText(self.tr("Convert UDM Result To SSU Results"))
        self.save_all_ssu_figures_action.setText(self.tr("Save Figures For All SSU Results"))
        self.language_menu.setTitle(self.tr("Language"))
        self.theme_menu.setTitle(self.tr("Theme"))
        self.log_action.setText(self.tr("Log"))
        self.about_action.setText(self.tr("About"))
        self.tab_widget.setTabText(0, self.tr("Generator"))
        self.tab_widget.setTabText(1, self.tr("Statistics"))
        self.tab_widget.setTabText(2, self.tr("PCA"))
        self.tab_widget.setTabText(3, self.tr("Clustering"))
        self.tab_widget.setTabText(4, self.tr("SSU"))
        self.tab_widget.setTabText(5, self.tr("EMMA"))
        self.tab_widget.setTabText(6, self.tr("UDM"))
        self.ssu_multicore_analyzer.retranslate()


def qgrain_app():
    app, splash = setup_app()
    main = MainWindow()
    # load the artificial dataset to show the functions of all modules
    dataset = main.dataset_generator.get_random_dataset(100)
    main.load_dataset_dialog.dataset_loaded.emit(dataset.dataset)
    main.ssu_analyzer.on_try_fit_clicked()
    from ..models import DistributionType, SSUResult
    from ..ssu import try_ssu
    sample = dataset[0]
    x0 = dataset.parameters[0, 1:, :]
    result, msg = try_ssu(sample.sample, DistributionType.Normal, dataset.n_components, x0=x0)
    assert isinstance(result, SSUResult)
    main.parameter_editor.refer_ssu_result(result)
    main.parameter_editor.enabled_checkbox.setChecked(True)
    main.emma_analyzer.on_try_fit_clicked()
    main.udm_analyzer.on_try_fit_clicked()
    setup_logging(main.statusBar(), main.log_dialog)
    main.show()
    splash.finish(main)
    sys.exit(app.exec())
