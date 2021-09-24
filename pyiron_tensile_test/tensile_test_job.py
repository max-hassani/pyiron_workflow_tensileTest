import pandas as pd
from pyiron_base import PythonTemplateJob, DataContainer
import pandas
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
import requests
from SPARQLWrapper import SPARQLWrapper, JSON
import os
import owncloud


class TensileJob(PythonTemplateJob):
    def __init__(self, project, job_name):
        super(TensileJob, self).__init__(project, job_name)
        self.input = DataContainer(table_name='input')
        self._experimental_json = None
        self._actual_data = None
        self._elast_min_ind = 0
        self._elast_max_ind = 0
        self.output = DataContainer(table_name='output')
        self._endpoint = None

    @property
    def experimental_json(self):
        return self._experimental_json

    @experimental_json.setter
    def experimental_json(self, data_frame):
        self._experimental_json = data_frame

    @property
    def actual_data_set(self):
        return self._actual_data

    @actual_data_set.setter
    def actual_data_set(self, data_frame):
        if isinstance(data_frame, pd.DataFrame):
            self._actual_data = data_frame
        else:
            raise TypeError("the dataset should be of type pandas.DataFrame")

    @property
    def endpoint(self):
        return self._endpoint

    @endpoint.setter
    def endpoint(self, url):
        self._endpoint = SPARQLWrapper(url)

    def query_data_source(self, test_name='Tensile_Test'):
        self.input.test_name = test_name
        query = """
        prefix onto-discovery: <https:materialdigital.de/discovery#>
        prefix wikiba: <http://wikiba.se/ontology#>

        SELECT ?t ?dt ?link
        WHERE{
            ?t a onto-discovery:%s. 
            ?t onto-discovery:has_data_resource ?dt .
            ?dt onto-discovery:downloadable_from ?link .
        }""" % test_name
        self.endpoint.setQuery(query)
        self.endpoint.setReturnFormat(JSON)
        results = self.endpoint.query().convert()
        header2column = {}
        variables = results['head']['vars']
        for binding in results['results']['bindings']:
            for v in variables:
                if v not in header2column:
                    header2column[v] = []
                header2column[v] += [binding[v]['value']]
        _init_data_frame = pandas.DataFrame.from_dict(header2column)
        return _init_data_frame['link'][0]

    def get_dataset(self, url):
        try:
            oc = owncloud.Client.from_public_link(url)
            content = oc.get_file_contents('')
            self.experimental_json = pandas.read_json(content)
        except Exception as err_msg:
            raise Exception(f"Error: {err_msg}.Download of the file unsuccessful!,")

    def get_json(self):
        url = self._init_data_frame['link'][0]
        content = requests.get(url, headers={'PRIVATE-TOKEN': '{}'. format(os.environ['gitlab_token'])}).content
        self.experimental_json = pandas.read_json(content)

    def extract_stress_strain(self):
        datalist = self._experimental_json['test.series']['data']
        fields_units = self._experimental_json['test.series']['fields']
        df_fields_units = pandas.DataFrame(fields_units, columns = ['fields', 'units']) 
        fields = list(df_fields_units['fields'])
        self._actual_data = pandas.DataFrame(datalist, columns = fields) 
        self.input.strains = np.array(self._actual_data['Elongation_1'][:])
        self.input.stresses = np.array(self._actual_data['Tensile Stress'][:])
    
    def get_linear_segment(self):
        strain_0 = 0.0006
        elastic_limit = 0.09
        self._elast_min_ind = 0
        self._elast_max_ind = 0
        flag_init = 0
        flag_end = 0
        i = 0
        while flag_init == 0 or flag_end == 0:
            if self.input.strains[i] >= strain_0 and flag_init == 0:
                self._elast_min_ind = i
                flag_init = 1
            if self.input.strains[i] > elastic_limit:
                self._elast_max_ind = i - 1
                flag_end = 1
            i = i + 1

    def plot_stress_strain(self):
        plt.xlabel('strain, %')
        plt.ylabel('stress, MPa')
        plt.xlim(-1,60)
        plt.ylim(0,700)
        plt.plot(self.input.strains, self.input.stresses)

    def calc_elastic_modulus(self):
        self.get_linear_segment()
        strains = self.input.strains * 0.01
        lm = LinearRegression()
        _x = strains[self._elast_min_ind:self._elast_max_ind]
        _y = self.input.stresses[self._elast_min_ind:self._elast_max_ind]
        _x = _x.reshape(-1, 1)
        _y = _y.reshape(-1, 1)
        lm.fit(_x, _y)
        self.output.elastic_modulus = float(lm.coef_[0])/1000

    def to_hdf(self):
        hdf = self.project_hdf5
        hdf['TYPE'] = str(type(self))
        self.input.to_hdf(hdf=self.project_hdf5)
        self.output.to_hdf(hdf=self.project_hdf5)

    def from_hdf(self, hdf, group_name):
        self.input.from_hdf(hdf=self.project_hdf5)
        self.output.from_hdf(hdf=self.project_hdf5)

    def run_static(self):
        self.calc_elastic_modulus()
        self.to_hdf()
        self.status.finished = True

    def update_triple_store(self):
        query = '''
            prefix onto-discovery: <https:materialdigital.de/discovery#>
            prefix wikiba: <http://wikiba.se/ontology#> 
            INSERT DATA
            { GRAPH <https:materialdigital.de/discovery#tt0> { <https:materialdigital.de/discovery#qv4>  wikiba:quantityAmount  %f } }
        ''' % self.output.elastic_modulus
        self.endpoint.setQuery(query)
        self.endpoint.method = 'POST'
        self.endpoint.query()

    def verify_update(self):
        query = """
        prefix onto-discovery: <https:materialdigital.de/discovery#>
        prefix wikiba: <http://wikiba.se/ontology#>

        SELECT ?t ?E 
        WHERE{

        	?t a onto-discovery:Tensile_Test .
          	?t onto-discovery:young_s_modulus  ?modulus .
            ?modulus wikiba:quantityAmount ?E .

        }

        		"""
        self.endpoint.setQuery(query)
        self.endpoint.setReturnFormat(JSON)

        results = self.endpoint.query().convert()

        header2column = {}
        variables = results['head']['vars']
        for binding in results['results']['bindings']:
            for v in variables:
                if v not in header2column:
                    header2column[v] = []
                header2column[v] += [binding[v]['value']]

        df = pd.DataFrame.from_dict(header2column)
        if abs(float(df['E'].values[-1]) - self.output.elastic_modulus)/self.output.elastic_modulus < 0.001:
            print("correctly updated!")
            return True
        else:
            print("the update was unsuccessful!")
            return False
