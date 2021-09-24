from pyiron_base import JOB_CLASS_DICT, Project
from .tensile_test_job import TensileJob

JOB_CLASS_DICT['TensileJob'] = 'pyiron_tensile_test.tensile_test_job'
