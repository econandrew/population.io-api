import os, time, logging
import pandas as pd
from django.conf import settings


logger = logging.getLogger(__name__)


class HDF5DataStore(object):
    """ Alternative data store implementation, based on the HDF5 format. Potentially faster than the current CSV/filesystem-based implementation, but
        had occasional inexplicable HDF5ExtErrors with unclear causes.
    """

    def __init__(self, storeFilename=settings.DATA_STORE_PATH):
        # prepare the filesystem cache
        self._store = pd.HDFStore(storeFilename, mode='a' if settings.DATA_STORE_WRITABLE else 'r', complevel=9, complib='blosc')

        # if possible, initialize from data store, otherwise read the CSVs
        if self._store.get_node('data') and self._store.get_node('life_expectancy_ages'):
            self.initialize()
        else:
            logger.info('Base data not found in the data store, reading from CSV...')
            self.readCSVs()

    def registerTableBuilder(self, builder):
        self._extrapolation_table_builder = builder

    def initialize(self):
        start = time.clock()
        self.data = self._store.get('data')
        self.life_expectancy_ages = self._store.get('life_expectancy_ages')
        self.countries = pd.unique(self.data.Location).tolist()
        logger.info('Initialized data store in %.02f seconds', (time.clock()-start))

    def readCSVs(self):
        start = time.clock()
        self.data = pd.read_csv(settings.CSV_POPULATION_PATH)
        self.life_expectancy_ages = pd.read_csv(settings.CSV_LIFE_EXPECTANCY_PATH)
        self.countries = pd.unique(self.data.Location).tolist()
        self._store.put('data', self.data)
        self._store.put('life_expectancy_ages', self.life_expectancy_ages)
        logger.info('Parsed CSVs in %.02f seconds', (time.clock()-start))

    def __getitem__(self, item):
        sex, country = item
        return self.getOrGenerateExtrapolationTable(sex, country)

    def _buildTableKey(self, sex, country):
        return '%s/%s' % (sex, country)

    def storeExtrapolationTable(self, sex, country, table):
        start = time.clock()
        self._store.put(self._buildTableKey(sex, country), table)
        logger.info('Stored extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)

    def retrieveExtrapolationTable(self, sex, country):
        start = time.clock()
        table = self._store.get(self._buildTableKey(sex, country))
        logger.info('Retrieved extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)
        return table

    def generateExtrapolationTable(self, sex, country):
        start = time.clock()
        table = self._extrapolation_table_builder(sex, country)
        logger.info('Generated extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)
        if settings.DATA_STORE_WRITABLE:
            self.storeExtrapolationTable(sex, country, table)
        return table

    def getOrGenerateExtrapolationTable(self, sex, country):
        key = self._buildTableKey(sex, country)
        if self._store.get_node(key):
            return self.retrieveExtrapolationTable(sex, country)
        else:
            return self.generateExtrapolationTable(sex, country)


class PickleDataStore(object):
    """ Data store implementation based on reading the base CSVs (population and life expectancy) into memory and then fetching
        the cached tables as pickle files with predefined filenames in a local filesystem path.
    """

    def __init__(self):
        logger.info('Reading base data CSVs...')
        self.readCSVs()

    def registerTableBuilder(self, builder):
        self._extrapolation_table_builder = builder

    def readCSVs(self):
        start = time.clock()
        # population by single year of age and year from 1950-2100
        # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total
        self.data = pd.read_csv(settings.CSV_POPULATION_PATH)
        
        # life expectancy in 5 year bands @ 5 year intervals (except age 1)
        # region, sex, period, period start year, x0, **x1**, x5, x10, x15,...
        self.life_expectancy_ages = pd.read_csv(settings.CSV_LIFE_EXPECTANCY_PATH)
        
        # daily population projections 2013-2022
        # country, date (Y/M/D), pop total
        self.total_population = pd.read_csv(settings.CSV_TOTAL_POPULATION_PATH)
        
        # survival ratio in 5 year bands @ 5 year intervals
        # region, sex, period, period start year, x0, x5, x10, x15,...        
        self.survival_ratio = pd.read_csv(settings.CSV_SURVIVAL_RATIO_PATH)
        
        # continent, country mapping
        self.continent_countries = pd.read_csv(settings.CSV_CONTINENT_COUNTRIES)
        
        # births per day by country 1950 - 2100
        self.births_day_country = pd.read_csv(settings.CSV_BIRTHS_DAY_COUNTRY)
        
        self.countries = pd.unique(self.data.Location).tolist()
        logger.info('Parsed CSVs in %.02f seconds', (time.clock()-start))

    def __getitem__(self, item):
        sex, country = item
        return self.getOrGenerateExtrapolationTable(sex, country)

    def _buildTableKey(self, sex, country):
        return '%s/%s' % (sex, country)

    def _buildExtrapolationTableFilename(self, sex, country):
        key = '%s-%s' % (sex, country.replace(' ', '_'))
        return os.path.join(settings.DATA_STORE_PATH, key + '.pkl')

    def storeExtrapolationTable(self, sex, country, table):
        start = time.clock()
        table.to_pickle(self._buildExtrapolationTableFilename(sex, country))
        logger.info('Stored extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)

    def retrieveExtrapolationTable(self, sex, country):
        start = time.clock()
        table = pd.read_pickle(self._buildExtrapolationTableFilename(sex, country))
        logger.info('Retrieved extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)
        return table

    def generateExtrapolationTable(self, sex, country):
        start = time.clock()
        logger.info('Generating extrapolation table for (%s, %s)...', sex, country)
        table = self._extrapolation_table_builder(sex, country)
        logger.info('Generated extrapolation table for (%s, %s) in %.02f seconds', sex, country, time.clock()-start)
        if settings.DATA_STORE_WRITABLE:
            self.storeExtrapolationTable(sex, country, table)
        return table

    def getOrGenerateExtrapolationTable(self, sex, country):
        path = self._buildExtrapolationTableFilename(sex, country)
        if os.path.exists(path):
            return self.retrieveExtrapolationTable(sex, country)
        else:
            return self.generateExtrapolationTable(sex, country)


# the central data store instance we're gonna use
dataStore = PickleDataStore()
