# Copyright (C) 2013 Ion Torrent Systems, Inc. All Rights Reserved
from iondb.utils import toBoolean
import json
import uuid
from django.core.exceptions import ValidationError
import simplejson
from traceback import format_exc

from iondb.rundb.plan.page_plan.step_helper_types import StepHelperType
from django.contrib.auth.models import User
from iondb.rundb.models import PlannedExperiment, PlannedExperimentQC, QCType,\
    Project, Plugin, RunType, ApplicationGroup

from iondb.rundb.plan.page_plan.step_names import StepNames
from django.db import transaction
from iondb.rundb.plan.page_plan.plugins_step_data import PluginFieldNames
from iondb.rundb.plan.page_plan.output_step_data import OutputFieldNames
from iondb.rundb.plan.page_plan.save_plan_by_sample_step_data import SavePlanBySampleFieldNames
from iondb.rundb.plan.page_plan.barcode_by_sample_step_data import BarcodeBySampleFieldNames
from iondb.rundb.plan.page_plan.application_step_data import ApplicationFieldNames
from iondb.rundb.plan.page_plan.ionreporter_step_data import IonReporterFieldNames
from iondb.rundb.plan.page_plan.kits_step_data import KitsFieldNames
from iondb.rundb.plan.page_plan.reference_step_data import ReferenceFieldNames
from iondb.rundb.plan.page_plan.save_plan_step_data import SavePlanFieldNames
from iondb.rundb.plan.page_plan.save_template_step_data import SaveTemplateStepDataFieldNames 
from iondb.rundb.plan.page_plan.analysis_params_step_data import AnalysisParamsFieldNames

import logging
logger = logging.getLogger(__name__)

class StepHelperDbSaver():

    def getProjectObjectList(self, step_helper, username):
        retval = []
        if step_helper.steps[StepNames.OUTPUT].savedFields[OutputFieldNames.PROJECTS]:
            for project_id in step_helper.steps[StepNames.OUTPUT].savedFields[OutputFieldNames.PROJECTS]:
                retval.append(Project.objects.get(id=int(project_id)))
        
        newProjectNames = step_helper.steps[StepNames.OUTPUT].savedFields[OutputFieldNames.NEW_PROJECTS]
        if newProjectNames:
            newProjectNames = newProjectNames.split(',')
            retval.extend(Project.bulk_get_or_create(newProjectNames, User.objects.get(username=username)))
        return retval

    def __get_universal_params(self, step_helper, username):
        if not step_helper.isPlan():
            if step_helper.isTemplateBySample():
                save_template_step_data = step_helper.steps[StepNames.SAVE_TEMPLATE_BY_SAMPLE]
            else:
                save_template_step_data = step_helper.steps[StepNames.SAVE_TEMPLATE]
                
        
        application_step_data = step_helper.steps[StepNames.APPLICATION]
        kits_step_data = step_helper.steps[StepNames.KITS]
        reference_step_data = step_helper.steps[StepNames.REFERENCE]
        plugins_step_data = step_helper.steps[StepNames.PLUGINS]
        ionreporter_step_data = step_helper.steps[StepNames.IONREPORTER]
        analysisParams_step_data = step_helper.steps[StepNames.ANALYSIS_PARAMS]

        isFavorite = False

        categories =  application_step_data.prepopulatedFields.get(ApplicationFieldNames.CATEGORIES, "")

        runType = ""
        if application_step_data.savedObjects[ApplicationFieldNames.RUN_TYPE]:
            runType = application_step_data.savedObjects[ApplicationFieldNames.RUN_TYPE].runType 
                           
        #if user has changed the application or target technique during template copying, reset categories value        
        applicationGroup = application_step_data.savedFields[ApplicationFieldNames.APPLICATION_GROUP]
        applicationGroupNames = ApplicationGroup.objects.filter(pk = applicationGroup)
        if (applicationGroupNames):
            applicationGroupName = applicationGroupNames[0].name
        else:
            applicationGroupName = application_step_data.prepopulatedFields.get(ApplicationFieldNames.APPLICATION_GROUP_NAME, "")
        
        #if user has changed the application or target technique during template copying, reset categories value
        if applicationGroupName != "DNA + RNA":
            #workaround: OCP DNA has DNA as applicationGroupName and AMPS as run type so it can be ambiguous. 
            #If user creates/copies/edits a template or plan from an OCP template, preserve the categories that starts out with.
            if categories and applicationGroupName != "DNA" and runType != "AMPS":
                categories = categories.replace("Onconet", "");
                categories = categories.replace("Oncomine", ""); 

                            
        if not step_helper.isPlan():
            isFavorite = save_template_step_data.savedFields[SaveTemplateStepDataFieldNames.SET_AS_FAVORITE]
                               
        logger.debug(" step_helper_db_saver.__get_universal_params() applicationGroupName=%s; categories=%s" %(applicationGroupName, categories))

        #logger.debug("step_helper_db_saver.__get_universal_params() application_step_data.savedFields=%s" %(application_step_data.savedFields))

        application_group = None
        sampleGrouping = None
        if application_step_data.savedObjects[ApplicationFieldNames.RUN_TYPE]:
            application_group = application_step_data.savedObjects[ApplicationFieldNames.RUN_TYPE].applicationGroups.all()[0:1][0]
        
        if application_step_data.savedFields[ApplicationFieldNames.APPLICATION_GROUP]:
            application_group = ApplicationGroup.objects.get(pk=application_step_data.savedFields[ApplicationFieldNames.APPLICATION_GROUP])

        if ionreporter_step_data.savedFields[IonReporterFieldNames.SAMPLE_GROUPING]:
            sampleGrouping = ionreporter_step_data.savedObjects[IonReporterFieldNames.SAMPLE_GROUPING]

        templatingKitName = kits_step_data.savedFields[KitsFieldNames.TEMPLATE_KIT_NAME]
        controlSequencekitname = kits_step_data.savedFields[KitsFieldNames.CONTROL_SEQUENCE]
        samplePrepKitName = kits_step_data.savedFields[KitsFieldNames.SAMPLE_PREPARATION_KIT]
        if kits_step_data.savedFields[KitsFieldNames.READ_LENGTH] > 0:
            libraryReadLength = kits_step_data.savedFields[KitsFieldNames.READ_LENGTH]
        else:
            libraryReadLength = kits_step_data.savedFields[KitsFieldNames.LIBRARY_READ_LENGTH]
        templatingSize = kits_step_data.savedFields[KitsFieldNames.TEMPLATING_SIZE]
        
        x_barcodeId = kits_step_data.savedFields[KitsFieldNames.BARCODE_ID]
        x_chipType = kits_step_data.savedFields[KitsFieldNames.CHIP_TYPE]
        if not x_chipType:
            x_chipType = ''
        
        x_flows = kits_step_data.savedFields[KitsFieldNames.FLOWS]
        x_forward3primeadapter = kits_step_data.savedFields[KitsFieldNames.FORWARD_3_PRIME_ADAPTER]
        x_libraryKey = kits_step_data.savedFields[KitsFieldNames.LIBRARY_KEY]
        tfKey = kits_step_data.savedFields[KitsFieldNames.TF_KEY]
        x_librarykitname = kits_step_data.savedFields[KitsFieldNames.LIBRARY_KIT_NAME]
        x_sequencekitname = kits_step_data.savedFields[KitsFieldNames.SEQUENCE_KIT_NAME]
        x_isDuplicateReads = kits_step_data.savedFields[KitsFieldNames.IS_DUPLICATED_READS]
        x_base_recalibration_mode = kits_step_data.savedFields[KitsFieldNames.BASE_RECALIBRATE]        
        x_realign = kits_step_data.savedFields[KitsFieldNames.REALIGN]
        
        x_bedfile = reference_step_data.savedFields[ReferenceFieldNames.TARGET_BED_FILE]
        x_library = reference_step_data.savedFields[ReferenceFieldNames.REFERENCE]
        x_regionfile = reference_step_data.savedFields[ReferenceFieldNames.HOT_SPOT_BED_FILE]

        x_mixedTypeRNA_bedfile = reference_step_data.savedFields[ReferenceFieldNames.MIXED_TYPE_RNA_TARGET_BED_FILE]
        x_mixedTypeRNA_library = reference_step_data.savedFields[ReferenceFieldNames.MIXED_TYPE_RNA_REFERENCE]
        x_mixedTypeRNA_regionfile = reference_step_data.savedFields[ReferenceFieldNames.MIXED_TYPE_RNA_HOT_SPOT_BED_FILE]    
 
        x_beadfindargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_BEADFIND_SELECTED]
        x_analysisargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_ANALYSISARGS_SELECTED]
        x_prebasecallerargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_PREBASECALLER_SELECTED]
        x_calibrateargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_CALIBRATE_SELECTED]
        x_basecallerargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_BASECALLER_SELECTED]
        x_alignmentargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_ALIGNMENT_SELECTED]
        x_ionstatsargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_IONSTATS_SELECTED]
        
        x_thumbnailbeadfindargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_BEADFIND_SELECTED]
        x_thumbnailanalysisargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_ANALYSISARGS_SELECTED]
        x_prethumbnailbasecallerargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_PREBASECALLER_SELECTED]
        x_thumbnailcalibrateargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_CALIBRATE_SELECTED]
        x_thumbnailbasecallerargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_BASECALLER_SELECTED]
        x_thumbnailalignmentargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_ALIGNMENT_SELECTED]
        x_thumbnailionstatsargs = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_THUMBNAIL_IONSTATS_SELECTED]
        
        x_custom_args = analysisParams_step_data.savedFields[AnalysisParamsFieldNames.AP_CUSTOM] == "True"
                                              
        selectedPluginsValue = plugins_step_data.getSelectedPluginsValue()
        
        logger.debug("step_helper_db_saver.__get_universal_params() application_step_data.prepopulatedFields[planStatus]=%s" %(application_step_data.prepopulatedFields[ApplicationFieldNames.PLAN_STATUS]))
        logger.debug("step_helper_db_saver.__get_universal_params() isEditRun=%s; isEdit=%s; isIonChef=%s; isPlan=%s; isPlanBySample=%s" %(str(step_helper.isEditRun()), str(step_helper.isEdit()), str(step_helper.isIonChef()), str(step_helper.isPlan()), str(step_helper.isPlanBySample())))

        planStatus = application_step_data.prepopulatedFields[ApplicationFieldNames.PLAN_STATUS]

        #preserve the plan status during plan editing
        #Also, update the planStatus when InstrumentType is changed from OT to IC
        if step_helper.isCreate() or step_helper.isCopy():
            if step_helper.isIonChef():
                planStatus = "pending"
            else:
                planStatus = "planned"
        elif step_helper.isEdit() and not step_helper.isEditRun():
            isTemplatekitTypeChange = step_helper.getChangedFields().get('templatekitType',None)
            if isTemplatekitTypeChange:
                if isTemplatekitTypeChange[1] == 'IonChef':
                    planStatus = "pending"
                else:
                    planStatus = "planned"

        #logger.debug("step_helper_db_saver.__get_universal_params() planStatus=%s" %(planStatus))
            
        retval = {
            'applicationGroup': application_group,
            'sampleGrouping' : sampleGrouping, 
            'usePreBeadfind': True,
            'usePostBeadfind': False if step_helper.isProton() else True,
            'preAnalysis': True,
            'runType': runType,
            'templatingKitName': templatingKitName,
            'controlSequencekitname': controlSequencekitname,
            'runMode': 'single',
            'isSystem': False,
            'isPlanGroup': False,
            'username': username,
            'isFavorite': toBoolean(isFavorite, False),
            'pairedEndLibraryAdapterName': '',
            'samplePrepKitName': samplePrepKitName,
            'libraryReadLength' : libraryReadLength,
            'templatingSize' : templatingSize,
            'planStatus' : planStatus,
            'categories' : categories,
            
            'x_usePreBeadfind': True,
            'x_autoAnalyze': True,
            'x_barcodeId': x_barcodeId,
            'x_bedfile': x_bedfile,
            'x_chipType': x_chipType,
            'x_flows': x_flows,
            'x_forward3primeadapter': x_forward3primeadapter,
            'x_library': x_library,
            'x_libraryKey': x_libraryKey,
            'tfKey': tfKey,
            'x_librarykitname': x_librarykitname,
            'x_regionfile': x_regionfile,
            'x_selectedPlugins': selectedPluginsValue,
            'x_sequencekitname': x_sequencekitname,
            'x_variantfrequency': '',
            'x_isDuplicateReads': False if x_isDuplicateReads is None else x_isDuplicateReads,
            'x_base_recalibration_mode': "no_recal" if x_base_recalibration_mode is None else x_base_recalibration_mode,
            'x_realign': False if x_realign is None else x_realign,
            'x_mixedTypeRNA_bedfile': x_mixedTypeRNA_bedfile,
            'x_mixedTypeRNA_regionfile': x_mixedTypeRNA_regionfile,
            'x_mixedTypeRNA_library': x_mixedTypeRNA_library,
            "x_beadfindargs" : x_beadfindargs,
            "x_analysisargs" : x_analysisargs,
            "x_prebasecallerargs" : x_prebasecallerargs,
            "x_calibrateargs" : x_calibrateargs,
            "x_basecallerargs" : x_basecallerargs,
            "x_alignmentargs" : x_alignmentargs,
            "x_ionstatsargs" : x_ionstatsargs,
            "x_thumbnailbeadfindargs" : x_thumbnailbeadfindargs,
            "x_thumbnailanalysisargs" : x_thumbnailanalysisargs,
            "x_prethumbnailbasecallerargs" : x_prethumbnailbasecallerargs,
            "x_thumbnailcalibrateargs" : x_thumbnailcalibrateargs,
            "x_thumbnailbasecallerargs" : x_thumbnailbasecallerargs,
            "x_thumbnailalignmentargs" : x_thumbnailalignmentargs,
            "x_thumbnailionstatsargs" : x_thumbnailionstatsargs,
            "x_custom_args": x_custom_args,
        }
        return retval


    def __get_specific_params_by_sample(self, step_helper, index=0, sample_set_item_display_Name=None, sample_external_id='', sample_description='', sampleSet_uid=None, planTotal=1, tubeLabel = "", chip_barcode=""):
        save_step = step_helper.steps[StepNames.SAVE_PLAN_BY_SAMPLE]
        barcoding_step = step_helper.steps[StepNames.BARCODE_BY_SAMPLE]
        sampleset = save_step.savedObjects[SavePlanBySampleFieldNames.SAMPLESET]
        plugins_step_data = step_helper.steps[StepNames.PLUGINS]
        ionreporter_step_data = step_helper.steps[StepNames.IONREPORTER]

        isReusable = False
        barcodedSamples = None
        
        planDisplayedName = save_step.savedFields[SavePlanBySampleFieldNames.TEMPLATE_NAME]

        note = save_step.savedFields[SavePlanFieldNames.NOTE]

        LIMS_meta = save_step.savedFields[SavePlanFieldNames.LIMS_META]
        existing_meta = save_step.savedFields[SavePlanFieldNames.META]
        
        selectedPluginsValue = plugins_step_data.getSelectedPluginsValue()
         
        sampleTubeLabel = tubeLabel
        chipBarcode = chip_barcode
        if step_helper.isBarcoded():
            barcodedSamples = json.dumps(barcoding_step.savedObjects[SavePlanFieldNames.SAMPLE_TO_BARCODE])            
            sampleTubeLabel = barcoding_step.savedFields[SavePlanFieldNames.BARCODE_SAMPLE_TUBE_LABEL]                    
            chipBarcode = barcoding_step.savedFields[SavePlanFieldNames.CHIP_BARCODE_LABEL]
 
        retval = {'planDisplayedName': planDisplayedName,
                  'planName': planDisplayedName.replace(' ', '_'),
                  'sampleTubeLabel' : sampleTubeLabel.strip() if sampleTubeLabel else "",                  
                  'chipBarcode' : chipBarcode.strip() if chipBarcode else "",
                  'metaData' : self.__update_metaData_for_LIMS(existing_meta, LIMS_meta), 
                  'isReusable': isReusable,
                  'sampleSet': sampleset,
                  'sampleSet_planIndex' : index,
                  'sampleSet_uid' : sampleSet_uid,
                  'x_barcodedSamples': barcodedSamples,
                  # 'x_numberOfChips' : barcoding_step.savedFields[BarcodeBySampleFieldNames.NUMBER_OF_CHIPS],
                  'x_selectedPlugins': selectedPluginsValue,
                  'x_notes' : note,
                  'x_isSaveBySample' : True
                }
        if ionreporter_step_data.savedFields[IonReporterFieldNames.IR_WORKFLOW] != None:
            retval.update({'irworkflow' : ionreporter_step_data.savedFields[IonReporterFieldNames.IR_WORKFLOW]})
        if not step_helper.isBarcoded():
            retval.update({
                    'sampleSet_planTotal' : planTotal,
                    'x_sample_external_id': sample_external_id,
                    'x_sample_description': sample_description,
                    'x_sampleDisplayedName': sample_set_item_display_Name,
                    })
        else:
            retval.update({
                    'sampleSet_planTotal' : planTotal,
                    })

        return retval

    def __get_specific_params(self, step_helper, username, sample_name='', tube_label='', chip_barcode='',
                              sample_external_id='', sample_description='',
                              is_multi_sample=False):
        ionreporter_step_data = step_helper.steps[StepNames.IONREPORTER]
        if step_helper.isTemplateBySample():
            save_step_data = step_helper.steps[StepNames.SAVE_TEMPLATE_BY_SAMPLE]
        else:
            save_step_data = step_helper.steps[StepNames.SAVE_TEMPLATE]
            
        planDisplayedName = save_step_data.savedFields[SaveTemplateStepDataFieldNames.TEMPLATE_NAME]
        sampleTubeLabel = ''
        chipBarcode = ''
        isReusable = True
        note = ''
        LIMS_meta = ""
        meta = ""
        sample = ''
        sample_display_name = ''
        barcodedSamples = None
        if step_helper.isPlan():
            planDisplayedName = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.PLAN_NAME]
            if is_multi_sample:
                planDisplayedName += '_' + sample_name.strip()
            sampleTubeLabel = tube_label
            chipBarcode = chip_barcode
            isReusable = False
            note = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.NOTE]

            LIMS_meta = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.LIMS_META]
            existing_meta = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.META]
        
            sample = sample_name.strip().replace(' ', '_')
            sample_display_name = sample_name.strip()
            if step_helper.isBarcoded():
                barcodedSamples = json.dumps(step_helper.steps[StepNames.SAVE_PLAN].savedObjects[SavePlanFieldNames.SAMPLE_TO_BARCODE])
                sampleTubeLabel = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.BARCODE_SAMPLE_TUBE_LABEL]
                chipBarcode = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.CHIP_BARCODE_LABEL]

                #logger.debug("step_helper_db_saver.__get_specific_params() barcodedSamples=%s" %(barcodedSamples))   
        else:
            note = save_step_data.savedFields[SaveTemplateStepDataFieldNames.NOTE]

            LIMS_meta = save_step_data.savedFields[SaveTemplateStepDataFieldNames.LIMS_META]
            existing_meta = save_step_data.savedFields[SaveTemplateStepDataFieldNames.META]
        
        retval = {'planDisplayedName': planDisplayedName,
                  'planName': planDisplayedName.replace(' ', '_'),
                  ##'sampleTubeLabel' : sampleTubeLabel.strip().lstrip("0") if sampleTubeLabel else "",
                  'sampleTubeLabel' : sampleTubeLabel.strip() if sampleTubeLabel else "",
                  'chipBarcode' : chipBarcode.strip() if chipBarcode else "",
                  'metaData' : self.__update_metaData_for_LIMS(existing_meta, LIMS_meta), 
                  'isReusable': isReusable,
                  'x_notes': note,
                  'x_sample': sample,
                  'x_sample_external_id': sample_external_id,
                  'x_sample_description': sample_description,
                  'x_sampleDisplayedName': sample_display_name,
                  'x_barcodedSamples': barcodedSamples
                  }
        if ionreporter_step_data.savedFields[IonReporterFieldNames.IR_WORKFLOW] != None:
            retval.update({'irworkflow' : ionreporter_step_data.savedFields[IonReporterFieldNames.IR_WORKFLOW]})
        return retval
        

    def __update_metaData_for_LIMS(self, existingValue, input):
        logger.debug("ENTER step_helper_db_saver.__update_metaData_for_LIMS() existingValue=%s; input=%s" %(existingValue, input))

        newValue = existingValue
        if newValue is None:
            newValue = {}
            
        if input:
            data = input.strip()            
            logger.debug("step_helper_db_saver.__update_metaData_for_LIMS() data=%s;" %(data))
            
            if not existingValue:
                newValue = {}
                
            newValue["LIMS"] = []                            
            newValue["LIMS"].append(data)
            
        json_newValue = json.dumps(newValue)            
        #logger.debug("step_helper_db_saver.__update_metaData_for_LIMS()AFTER newValue=%s" %(newValue))        
        #logger.debug("step_helper_db_saver.__update_metaData_for_LIMS()AFTER type(json_newValue)=%s; json_newValue=%s" %(type(json_newValue), json_newValue))
        
        return json_newValue

                
    def __update_non_barcode_ref_info(self, step_helper, parentDict, sampleValueDict):
        """
        Overrides the plan's reference and BED file dictionary based on values in the sampleValueDict
        This is to support multi-chip planning
        """
        if not sampleValueDict:
            return
                   
        if SavePlanFieldNames.BARCODE_SAMPLE_REFERENCE in sampleValueDict.keys():
            parentDict["x_library"] = sampleValueDict[SavePlanFieldNames.BARCODE_SAMPLE_REFERENCE]
        if SavePlanFieldNames.BARCODE_SAMPLE_TARGET_REGION_BED_FILE in sampleValueDict.keys():
            parentDict["x_bedfile"] = sampleValueDict[SavePlanFieldNames.BARCODE_SAMPLE_TARGET_REGION_BED_FILE]
        if SavePlanFieldNames.BARCODE_SAMPLE_HOTSPOT_REGION_BED_FILE in sampleValueDict.keys():
            parentDict["x_regionfile"] = sampleValueDict[SavePlanFieldNames.BARCODE_SAMPLE_HOTSPOT_REGION_BED_FILE]


    def __update_plugins_with_ir(self, step_helper, parentDict, userInputList):
        logger.debug("step_helper_db_sever.__update_plugins_with_ir() userInputList=%s" %(userInputList))

        accountId = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IR_ACCOUNT_ID]
        
        if accountId and (accountId not in ['-1', '0']):

            ir_plugin = step_helper.steps[StepNames.IONREPORTER].prepopulatedFields[IonReporterFieldNames.IR_PLUGIN]
            accountName = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IR_ACCOUNT_NAME]
            #TS-11365 - Below comment will be reverted in release 5.2 and default settings (ir_qc_option) will be removed
            #ir_qc_option = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IRU_UPLOAD_MODE]
            ir_qc_option = 'no_check'

            try:
                is_IR_Down = step_helper.steps[StepNames.SAVE_PLAN].savedFields[SavePlanFieldNames.IR_DOWN] == '1'
            except:
                is_IR_Down = step_helper.steps[StepNames.BARCODE_BY_SAMPLE].savedFields[SavePlanFieldNames.IR_DOWN] == '1'


            if is_IR_Down:
                if (step_helper.isEdit() or step_helper.isCopy() or step_helper.isEditRun()) and step_helper.previous_plan_id > 0:
                    selectedPlugins = PlannedExperiment.objects.get(pk=step_helper.previous_plan_id).experiment.get_EAS().selectedPlugins
                    if selectedPlugins and 'IonReporterUploader' in selectedPlugins:
                        # update old userInputInfo sample information that may've changed
                        old_userInputInfo = selectedPlugins['IonReporterUploader'].get('userInput',{}).get('userInputInfo')
                        if old_userInputInfo and len(old_userInputInfo) == len(userInputList):
                            for old,new in zip(old_userInputInfo, userInputList):
                                old[SavePlanFieldNames.SAMPLE] = new[SavePlanFieldNames.SAMPLE]
                                old[SavePlanFieldNames.SAMPLE_NAME] = new[SavePlanFieldNames.SAMPLE_NAME]
                                old[SavePlanFieldNames.SAMPLE_EXTERNAL_ID] = new[SavePlanFieldNames.SAMPLE_EXTERNAL_ID]
                                old[SavePlanFieldNames.SAMPLE_DESCRIPTION] = new[SavePlanFieldNames.SAMPLE_DESCRIPTION]
                                if KitsFieldNames.BARCODE_ID in new:
                                    old[KitsFieldNames.BARCODE_ID] = new[KitsFieldNames.BARCODE_ID]

                            parentDict['x_selectedPlugins']['IonReporterUploader'] = selectedPlugins['IonReporterUploader']
            elif ir_plugin:
                suffix = '__'+ str(uuid.uuid4())
                if step_helper.isEdit() or step_helper.isCopy():
                    try:
                        suffix = step_helper.steps[StepNames.SAVE_PLAN].prepopulatedFields.get('setid_suffix', suffix)
                    except:
                        suffix = step_helper.steps[StepNames.BARCODE_BY_SAMPLE].prepopulatedFields.get('setid_suffix', suffix)

                parentDict['x_selectedPlugins']['IonReporterUploader'] = self.__get_ir_plugins_entry(ir_plugin, userInputList, accountId, accountName, suffix, ir_qc_option)


    def __get_ir_plugins_entry(self, ir_plugin, userInputList, accountId, accountName, suffix, ir_qc_option):
        ir_plugin_dict = {
            PluginFieldNames.PL_ID: ir_plugin.id,
            PluginFieldNames.NAME: ir_plugin.name,
            PluginFieldNames.VERSION: ir_plugin.version,
            PluginFieldNames.FEATURES: [PluginFieldNames.EXPORT],
        }

        for userInput in userInputList:
            if userInput['Workflow'] == 'Upload Only': userInput['Workflow'] = ''

            # add unique suffix to setid value
            setid = userInput.get('setid') or ''
            userInput['setid'] = setid + suffix

        ir_plugin_dict[PluginFieldNames.USER_INPUT] = {
            PluginFieldNames.ACCOUNT_ID: accountId,
            PluginFieldNames.ACCOUNT_NAME: accountName,
            PluginFieldNames.ACCOUNT_NAME: accountName,
            PluginFieldNames.IRU_QC_OPTIONS: ir_qc_option,
            "userInputInfo": userInputList
        }
        return ir_plugin_dict

    @transaction.commit_manually
    def save(self, step_helper, username):
        try:
            if step_helper.isPlanBySample() or step_helper.isTemplateBySample():
                planTemplate = self.__innser_save_by_sample(step_helper, username)
            else:
                planTemplate = self.__innser_save(step_helper, username)
            transaction.commit()

            return planTemplate
        except ValidationError, err:
            transaction.rollback()
            logger.exception(format_exc())
            message = "Internal error while trying to save the plan. "
            for msg in err.messages:                
                message += str(msg)
                message += " "
            raise ValueError(message)
        except Exception as excp:
            transaction.rollback()
            logger.exception(format_exc())
            message = "Internal error while trying to save the plan. %s" %(excp.message)
            raise ValueError(message)
        except:
            transaction.rollback()
            logger.exception(format_exc())
            raise ValueError("A completely unexpected error has occurred while trying to save plan.")


            
    def __innser_save_by_sample(self, step_helper, username):        
        projectObjList = self.getProjectObjectList(step_helper, username)
        sampleSet_uid = str(uuid.uuid4())
        if step_helper.isPlanBySample():
            barcoding_step_data = step_helper.steps[StepNames.BARCODE_BY_SAMPLE]
            
            if step_helper.isBarcoded():
                kwargs = self.__get_universal_params(step_helper, username)
                kwargs.update(self.__get_specific_params_by_sample(step_helper, sampleSet_uid=sampleSet_uid))
                self.__update_plugins_with_ir(step_helper, kwargs, barcoding_step_data.savedObjects[SavePlanFieldNames.IR_PLUGIN_ENTRIES])

                if step_helper.sh_type == StepHelperType.EDIT_PLAN_BY_SAMPLE and step_helper.previous_plan_id > 0:
                    self.savePlannedExperiment(step_helper, kwargs, projectObjList, step_helper.previous_plan_id)
                elif step_helper.sh_type == StepHelperType.CREATE_NEW_TEMPLATE_BY_SAMPLE:
                    self.saveTemplate(step_helper, username, projectObjList)
                else:
                    self.savePlannedExperiment(step_helper, kwargs, projectObjList)
            else:
                sampleDicts = []
                for values in barcoding_step_data.savedObjects[SavePlanFieldNames.SAMPLES_TABLE_LIST]:
                    sampleName = values['sampleName']
                    if sampleName:
                        sampleDicts.append(values)
                
                isMultiSample = len(sampleDicts) > 1
                
                firstIteration = True
                suffix = str(uuid.uuid4())
                for index, valueDict in enumerate(sampleDicts):
                    kwargs = self.__get_universal_params(step_helper, username)
                    kwargs.update(self.__get_specific_params_by_sample(step_helper, index=index, \
                            sample_set_item_display_Name=valueDict[SavePlanFieldNames.SAMPLE_NAME], sample_external_id=valueDict[SavePlanFieldNames.SAMPLE_EXTERNAL_ID], sample_description=valueDict[SavePlanFieldNames.SAMPLE_DESCRIPTION], \
                            sampleSet_uid=sampleSet_uid, planTotal=len(sampleDicts), tubeLabel=valueDict[SavePlanFieldNames.TUBE_LABEL], chip_barcode=valueDict[SavePlanFieldNames.CHIP_BARCODE]))

                    self.__update_non_barcode_ref_info(step_helper, kwargs, valueDict)
                    
                    self.__update_plugins_with_ir(step_helper, kwargs, [ barcoding_step_data.savedObjects[SavePlanFieldNames.IR_PLUGIN_ENTRIES][index] ])
                    
                    if step_helper.sh_type == StepHelperType.EDIT_PLAN_BY_SAMPLE and step_helper.previous_plan_id > 0 and firstIteration:
                        self.savePlannedExperiment(step_helper, kwargs, projectObjList, step_helper.previous_plan_id)
                    else:
                        self.savePlannedExperiment(step_helper, kwargs, projectObjList)
                    firstIteration = False 
        else:
            return self.saveTemplate(step_helper, username, projectObjList)

    def __innser_save(self, step_helper, username):
        projectObjList = self.getProjectObjectList(step_helper, username)
        if step_helper.isPlan():
            save_plan_step_data = step_helper.steps[StepNames.SAVE_PLAN]
            
            if step_helper.isBarcoded():
                kwargs = self.__get_universal_params(step_helper, username)
                kwargs.update(self.__get_specific_params(step_helper, username, '', '', False))

                logger.debug("step_helper_db_saver.__innser_save() isBarcoded - AFTER UPDATE kwargs=%s" %(kwargs))
                
                self.__update_plugins_with_ir(step_helper, kwargs, save_plan_step_data.savedObjects[SavePlanFieldNames.IR_PLUGIN_ENTRIES])
                if step_helper.sh_type in [StepHelperType.EDIT_PLAN, StepHelperType.EDIT_RUN] and step_helper.previous_plan_id > 0:
                    self.savePlannedExperiment(step_helper, kwargs, projectObjList, step_helper.previous_plan_id)
                else:
                    self.savePlannedExperiment(step_helper, kwargs, projectObjList)
            else:
                sampleDicts = []
                for values in save_plan_step_data.savedObjects[SavePlanFieldNames.SAMPLES_TABLE_LIST]:
                    sampleName = values['sampleName']
                    if sampleName:
                        sampleDicts.append(values)
                
                isMultiSample = len(sampleDicts) > 1
                
                firstIteration = True
                for index, valueDict in enumerate(sampleDicts):
                    #logger.debug("__innser_save() sampleDicts - valueDict=%s" %(valueDict))
                    
                    kwargs = self.__get_universal_params(step_helper, username)
                    kwargs.update(self.__get_specific_params(step_helper, username, valueDict[SavePlanFieldNames.SAMPLE_NAME], valueDict[SavePlanFieldNames.TUBE_LABEL], valueDict[SavePlanFieldNames.CHIP_BARCODE],
                                                             valueDict[SavePlanFieldNames.SAMPLE_EXTERNAL_ID], valueDict[SavePlanFieldNames.SAMPLE_DESCRIPTION], isMultiSample))

                    self.__update_non_barcode_ref_info(step_helper, kwargs, valueDict)

                    self.__update_plugins_with_ir(step_helper, kwargs, [ save_plan_step_data.savedObjects[SavePlanFieldNames.IR_PLUGIN_ENTRIES][index] ])
                    
                    if step_helper.sh_type in [StepHelperType.EDIT_PLAN, StepHelperType.EDIT_RUN] and step_helper.previous_plan_id > 0 and firstIteration:
                        self.savePlannedExperiment(step_helper, kwargs, projectObjList, step_helper.previous_plan_id)
                    else:
                        self.savePlannedExperiment(step_helper, kwargs, projectObjList)
                    firstIteration = False
        else:
            return self.saveTemplate(step_helper, username, projectObjList)

    def saveTemplate(self, step_helper, username, projectObjList):
        logger.debug("step_helper_db_saver.saveTemplate() isCopy=%s; isCreate=%s; isEdit=%s; isEditRun=%s" %(str(step_helper.isCopy()), str(step_helper.isCreate()), str(step_helper.isEdit()), str(step_helper.isEditRun())))
        
        kwargs = self.__get_universal_params(step_helper, username)
        kwargs.update(self.__get_specific_params(step_helper, username))

        accountId = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IR_ACCOUNT_ID]
        if accountId and (accountId not in ['-1', '0']):
            accountName = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IR_ACCOUNT_NAME]
            #TS-11365 - Below comment will be reverted in release 5.2 and default settings (ir_qc_option) will be removed
            #ir_qc_option = step_helper.steps[StepNames.IONREPORTER].savedFields[IonReporterFieldNames.IRU_UPLOAD_MODE]
            ir_qc_option = 'no_check'
            kwargs['x_selectedPlugins']['IonReporterUploader'] = self.__get_ir_plugins_entry(step_helper.steps[StepNames.IONREPORTER].prepopulatedFields[IonReporterFieldNames.IR_PLUGIN],
                                                                                             '', accountId, accountName, '', ir_qc_option)

        logger.debug("step_helper_db_saver.saveTemplate() sh_type=%s; previous_template_id=%s" %(step_helper.sh_type, str(step_helper.previous_template_id)))

        if step_helper.sh_type == StepHelperType.EDIT_TEMPLATE and step_helper.previous_template_id > 0:
            return self.savePlannedExperiment(step_helper, kwargs, projectObjList, step_helper.previous_template_id)
        else:
            return self.savePlannedExperiment(step_helper, kwargs, projectObjList)

    def savePlannedExperiment(self, step_helper, param_dict, projectObjList, pe_id_to_update=None):
        planTemplate = None
        #if we're changing a plan from having 1 sample to say 2 samples, we need to UPDATE 1 plan and CREATE 1 plan!!
        logger.debug("About to savePlannedExperiment, KWARGS ARE: %s" % str(param_dict))
        for key,value in sorted(param_dict.items()):
            logger.debug('KWARG %s: %s' % (str(key), str(value)))
        if pe_id_to_update:
            logger.debug("step_helper_db_saver.savePlannedExperiment() pe_id_to_update=%s" %(str(pe_id_to_update)))
            planTemplate, extra_kwargs = PlannedExperiment.objects.save_plan(pe_id_to_update, **param_dict)
        else:
            planTemplate, extra_kwargs = PlannedExperiment.objects.save_plan(-1, **param_dict)

        if step_helper.isPlanBySample():
            self.saveQc(planTemplate, step_helper.steps[StepNames.SAVE_PLAN_BY_SAMPLE])
        elif step_helper.isTemplate():
            if step_helper.isTemplateBySample():
                self.saveQc(planTemplate, step_helper.steps[StepNames.SAVE_TEMPLATE_BY_SAMPLE])
            else:
                self.saveQc(planTemplate, step_helper.steps[StepNames.SAVE_TEMPLATE])
        else:
            self.saveQc(planTemplate, step_helper.steps[StepNames.SAVE_PLAN])
        self.saveProjects(planTemplate, projectObjList)
        self.addSavedPlansList(planTemplate.pk)
        return planTemplate
            

    def saveQc(self, planTemplate, monitoring_step):
        # Update QCtype thresholds
        qcTypes = QCType.objects.all()
        for qcType in qcTypes:
            qc_threshold = monitoring_step.savedFields[qcType.qcName]
            if qc_threshold:
                # get existing PlannedExperimentQC if any
                plannedExpQcs = PlannedExperimentQC.objects.filter(plannedExperiment=planTemplate.id, qcType=qcType.id)
                if len(plannedExpQcs) > 0:
                    for plannedExpQc in plannedExpQcs:
                        plannedExpQc.threshold = qc_threshold
                        plannedExpQc.save()
                else:
                    kwargs = {
                        'plannedExperiment': planTemplate,
                        'qcType': qcType,
                        'threshold': qc_threshold
                    }
                    plannedExpQc = PlannedExperimentQC(**kwargs)
                    plannedExpQc.save()

    def saveProjects(self, planTemplate, projectObjList):
        # add/remove projects
        if projectObjList:
            #TODO: refactor this logic to simplify using django orm
            projectNameList = [project.name for project in projectObjList]
            for currentProject in planTemplate.projects.all():
                if currentProject.name not in projectNameList:
                    planTemplate.projects.remove(currentProject)
            for projectObj in projectObjList:
                planTemplate.projects.add(projectObj)
        else:
            planTemplate.projects.clear()
            
    def addSavedPlansList(self, plan_pk):
        if plan_pk and plan_pk > 0:
            if hasattr(self, 'saved_plans'):
                self.saved_plans.append(plan_pk)
            else:
                self.saved_plans = [plan_pk]
    
    def getSavedPlansList(self):
        return getattr(self, 'saved_plans', '')
