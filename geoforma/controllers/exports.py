"""ExportWorkflow responsibilities in the Qt application layer."""
from __future__ import annotations
from ..ui.text import ui_text
import copy
from pathlib import Path
from PySide6.QtWidgets import QFileDialog, QMessageBox
from ..raster import validate_grid


class ExportWorkflow:
    def refresh_export_label_field(self,force=False):
        control=self.export_label_field_input
        if not force and control.hasFocus() and control.isModified():return
        from ..export_settings import label_field
        value=label_field(self.project)
        if control.text()!=value:control.setText(value)
        if force:control.setModified(False)

    def commit_export_label_field(self):
        from ..export_settings import validate_label_field,DEFAULT_LABEL_FIELD
        try:value=validate_label_field(self.export_label_field_input.text())
        except ValueError as error:
            self.refresh_export_label_field(force=True);self.statusBar().showMessage(str(error),7000);return False
        if value!=self.project.get('export_label_field',DEFAULT_LABEL_FIELD):
            self.project['export_label_field']=value;self.mark_dirty()
        self.refresh_export_label_field(force=True);return True

    def refresh_export_crs(self,force=False):
        if not force and self.export_crs_input.hasFocus() and self.export_crs_input.isModified():return
        from ..export_settings import target_crs
        try:value=target_crs(self.project,self.image)
        except ValueError:value=''
        if self.export_crs_input.text()!=value:self.export_crs_input.setText(value)
        if force:self.export_crs_input.setModified(False)

    def set_export_crs(self,value):
        from rasterio.crs import CRS
        value=value.strip();value=CRS.from_user_input(value).to_string() if value else ''
        from ..export_settings import target_crs
        try:default=target_crs(dict(self.project,export_crs=''),self.image)
        except ValueError:default=''
        if value==default:value=''
        if value!=self.project.get('export_crs',''):
            self.project['export_crs']=value;self.mark_dirty()
        self.refresh_export_crs(force=True)

    def commit_export_crs(self):
        try:self.set_export_crs(self.export_crs_input.text())
        except Exception:
            self.refresh_export_crs(force=True);self.statusBar().showMessage(ui_text('exports.commit_export_crs.010'),5000)

    def export(self,kind):
        if not self.image or self.foreground_task_active() or kind!='gpkg':return
        if not self.commit_export_label_field():return
        labels=copy.deepcopy([l for l in self.current_labels() if l['status']=='confirmed'])
        if not labels:QMessageBox.information(self,ui_text('exports.export.005'),ui_text('exports.export.006'));return
        ext='gpkg';name=Path(self.image['path']).stem+'_labels.'+ext
        filters='GeoPackage (*.gpkg);;Shapefile (*.shp);;GeoJSON (*.geojson)'
        path,selected=QFileDialog.getSaveFileName(self,ui_text('exports.export.003'),str((self.project_path.parent if self.project_path else Path.cwd())/name),filters)
        if not path:return
        supported=['.gpkg','.shp','.geojson']
        if Path(path).suffix.lower() not in supported:
            extension='.shp' if '*.shp' in selected else '.geojson' if '*.geojson' in selected else '.gpkg'
            path=str(Path(path).with_name(Path(path).name+extension))
        from ..export_settings import target_crs,label_field,validate_label_field
        image=copy.deepcopy(self.image)
        try:
            crs=target_crs(self.project,image) if Path(path).suffix.lower()!='.geojson' else ''
            field=validate_label_field(label_field(self.project),Path(path).suffix)
        except ValueError as e:self.error(str(e));return
        classes=copy.deepcopy(self.project['classes'])
        from ..source_catalog import project_sources
        sources=copy.deepcopy(project_sources(self.project))
        from ..smoothing import settings,smooth_batch
        smoothing=settings(self.project,self.annotation_mode())
        def work(task):
            from ..exports import export_vector
            validate_grid(image)
            output=[dict(label,smoothing_applied=smoothing['value']) for label in smooth_batch(labels,smoothing['value'],image,task)] if smoothing['enabled'] else labels
            result=export_vector(image,output,path,crs,task,classes,sources=sources,label_field=field)
            return result
        def exported(result):
            note=ui_text('exports.exported.009') if Path(result).suffix.lower()=='.shp' else ui_text('exports.exported.012') if Path(result).suffix.lower()=='.geojson' else ''
            self.log_message(ui_text('exports.exported.013')+result+note);self.statusBar().showMessage(Path(result).suffix[1:].upper()+(' · EPSG:4326' if Path(result).suffix.lower()=='.geojson' else ''),5000)
        self.run(ui_text('exports.export.004'),work,exported,kind='export')

