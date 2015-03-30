import pandas as pd
import os.path
import population

###################################################################################################
# This file is a very rough cut of the relevant code from the previous implementation so I could
# test it without needing Django dependencies working. Ideally, if we want to keep the old
# implementation around, we should restructure it more smoothly as a PopulationModel.
###################################################################################################

###################################################################################################
# A wrapper class for the previous method, for comparisons
###################################################################################################

class OriginalDailyPopulationModel(population.DailyPopulationModel):
    sexmap = {'M': 'male', 'F': 'female'}

    def __init__(self, base_model):
        super(OriginalDailyPopulationModel, self).__init__(base_model)

    def pop_age(self, date, region, sex, age):
        raise NotImplemented

    def pop_sum_dob(self, date, region, sex, dob_from = None, dob_to = None):
        if dob_to != date:
            raise NotImplemented("Not implemented for the general case")

        return population_original.worldPopulationRankByDate(
            self.sexmap[sex],
            region,
            population.from_epoch_days(dob_from),
            population.from_epoch_days(date)
        )

    def pop_sum_dob_inverse_date(self, pop, region, sex, dob_from):
        return population.to_epoch_days(dateByWorldPopulationRank(
            self.sexmap[sex],
            region,
            population.from_epoch_days(dob_from),
            pop
        ))


class PickleDataStore(object):
    """ Data store implementation based on reading the base CSVs (population and life expectancy) into memory and then fetching
        the cached tables as pickle files with predefined filenames in a local filesystem path.
    """

    def __init__(self):
        self.DATA_STORE_WRITABLE = True
        self.CSV_POPULATION_PATH = "../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv"
        self.DATA_STORE_PATH = os.path.dirname(os.path.abspath(self.CSV_POPULATION_PATH))
        self.readCSVs()

    def registerTableBuilder(self, builder):
        self._extrapolation_table_builder = builder

    def readCSVs(self):
        # population by single year of age and year from 1950-2100
        # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total
        self.data = pd.read_csv(self.CSV_POPULATION_PATH)
        self.countries = pd.unique(self.data.Location).tolist()

    def __getitem__(self, item):
        sex, country = item
        return self.getOrGenerateExtrapolationTable(sex, country)

    def _buildTableKey(self, sex, country):
        return '%s/%s' % (sex, country)

    def _buildExtrapolationTableFilename(self, sex, country):
        key = '%s-%s' % (sex, country.replace(' ', '_'))
        return os.path.join(self.DATA_STORE_PATH, key + '.pkl')

    def storeExtrapolationTable(self, sex, country, table):
        table.to_pickle(self._buildExtrapolationTableFilename(sex, country))

    def retrieveExtrapolationTable(self, sex, country):
        table = pd.read_pickle(self._buildExtrapolationTableFilename(sex, country))
        return table

    def generateExtrapolationTable(self, sex, country):
        table = self._extrapolation_table_builder(sex, country)
        if self.DATA_STORE_WRITABLE:
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

import math
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd
from scipy.interpolate import InterpolatedUnivariateSpline

from utils import relativedelta_to_decimal_years



# AGE in days refering to the annual data - we assume that the average age of one years old is 1 years and 183 days
AGE3 = [x*365+183 for x in range(0,100)]

# Range of days (age)
AGEOUT = range(0, 36501)

SEXES = {'male': 'PopMale', 'female': 'PopFemale', 'unisex': 'PopTotal',}
SEXES_LIFE_EXPECTANCY = {'male': 1, 'female': 2,}

POSIX_EPOCH = date(1970, 1, 1)
def inPosixDays(date):
    """
    Transforms a datetime object into 'posix days', here defined as the days since the posix epoch, Jan 1, 1970.

    :param date: a datetime object
    :return: the corresponding 'posix days' to the given datetime object
    """
    return (date - POSIX_EPOCH).days

def generateExtrapolationTable(sex, region):
    """
    Function that extrapolates the 1st July data to each calender day

    :param region: valid values: anything from 'regions'
    :param sex: valid values: female, male, unisex
    :return: an extrapolation table for the given region/sex tuple
    """
    pop1 = dataStore.data[dataStore.data.Location == region]
    pop1 = pop1[['Time', 'Age', SEXES[sex]]]
    # pop1 = data[['Time', 'Age', SEX]].query('Location' == CNTRY)
    #print pop1

    # pop1 now has {year, age, popn} for the given country and sex 1950-2100

    july1from1950to2100 = [inPosixDays(date(y, 7, 1)) for y in xrange(1950, 2100+1)]

    dateRange1950to2100inPosixDays = range(inPosixDays(date(1950,1,1)), inPosixDays(date(2100,12,31))+1)

    ''' --- Date interpolation function --- '''
    def dateInterp(iage):
        """"
        Given an empty column representing a single 5 year age band, interpolate external popn data
        from yearly to daily data using splines, and return the daily population counts.
        """
        popi = np.asarray(pop1.loc[dataStore.data.Age == iage.name, SEXES[sex]])
        # popi is now a single column of yearly population for a given age and sex

        # spline interpolation function from Scipy Package
        iuspl = InterpolatedUnivariateSpline(july1from1950to2100, popi, k=4)
        return iuspl(dateRange1950to2100inPosixDays)

    # --- store the results of the date interpolation --- #
    result1 = pd.DataFrame(index = range(0,len(dateRange1950to2100inPosixDays)), columns = range(0,100))    
    table = result1.apply(dateInterp, axis=0)

    # Change column names by appending "age_"
    oldHeaders = table.columns
    newHeaders = []
    for i in oldHeaders:
        newHeaders.append("age" + "_" + str(i))
    table.columns = newHeaders
    #print result1.head # results: "age_0, age_1, ..."

    # Convert the numerical days to date string
    def toDate(d):
        return (date(1970, 1, 1) + timedelta(days=d)).strftime('%Y-%m-%d')
    toDate = np.vectorize(toDate) # vectorize the function to iterate over numpy ndarray
    #fullDateRange = toDate(dateRange1970to2100inPosixDays) # 1st result: 1950-01-01
    fullDateRange = len(dateRange1950to2100inPosixDays)*[None]
    for i in range(0,len(dateRange1950to2100inPosixDays)):
        fullDateRange[i] = toDate(dateRange1950to2100inPosixDays[i])

    # Add the fullDateRange to the result1
    table['date1'] = fullDateRange

    # table will now be a crosstab of integer days (1950-2100) x single year of age (age_0-age_99)
    # with a date type column appended

    return table
    
dataStore.registerTableBuilder(generateExtrapolationTable)   # TODO: not super nice architecture, but avoids the cyclic dependency for now

def dayInterpA(table, date):
    """
    function that interpolates age in days

    :param table: the extrapolation table to use
    :param date: the date
    :return:
    """
    iDate = date.strftime('%Y-%m-%d')
    # age 0 to 99 - select a row containing popn by each single year of age for the given date
    popi = table[table.date1 == iDate]

    # Remove the columns for age 100 and the date1
    popi = popi.iloc[:,0:100]

    # store the popi results into an array for the interpolation
    #popi = (np.asarray(popi)).tolist()
    popi = np.asarray(popi)

    # Interpolate the age in Days
    # NOTE: this seems like a bad way to interpolate this - is it the case that
    # the spline-interpolate population over the days of a year will necessarily
    # add back up to the population in that year. Check this.
    iuspl2 = InterpolatedUnivariateSpline(AGE3, popi/365)
    iuspl2_pred = iuspl2(AGEOUT)

    # the output
    merged = pd.DataFrame(index = range(0,len(AGEOUT)), columns = ['AGE','POP'])
    merged['AGE'] = AGEOUT
    merged['POP'] = iuspl2_pred
    
    # CHECK: probably returns a frame containing popn by single day of age for the given date
    return merged

def _calculateRankByDate(table, dob, date):
    """
    Returns the rank of a person born on dob for the given sex/country represented by table,
    on the given date, if you lined up everybody by exact age in days from youngest to oldest.
    """
    
    # do the interpolation
    iAge = inPosixDays(date) - inPosixDays(dob)   # age in days at date # FIXME: isn't this just (date - dob).days?
    X = dayInterpA(table, date) # X is the entire population count by single day of age on date

    # store age and pop in array
    ageArray = np.asarray(X.AGE)
    popArray = np.asarray(X.POP)

    # calc cumulative sum of the population
    cumSum =  np.cumsum(popArray)

    # take the mean of the cumulative sum of the iAge year and preceeding
    rank = np.mean(np.extract((ageArray >= iAge -1) & (ageArray <= iAge), cumSum))
    if not rank > 0:
        raise RuntimeError('Rank calculation failed due to internal error')   # we should never get here, if we do that means the parameter checks at the beginning are incomplete
    return rank

def worldPopulationRankByDate(sex, region, dob, refdate):
    """
    my rank by date: What will be my rank on particular day

    :param sex:
    :param region:
    :param dob:
    :param refdate:
    :return:
    """
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(sex, basestring) or not isinstance(region, basestring) or not isinstance(dob, date) or not isinstance(refdate, date):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if sex not in SEXES:
        raise InvalidSexError(sex)
    if region not in dataStore.countries:
        raise InvalidCountryError(region)

    # check the various date requirements
    today = datetime.utcnow().date()
    if dob < date(1920, 1, 1) or dob > today:
        raise BirthdateOutOfRangeError(dob, 'between 1920-01-01 and today')
    if refdate < date(1950, 1, 1) or refdate < dob:
        raise CalculationDateOutOfRangeError(refdate, 'past 1950-01-01 and past the birthdate')
    if (refdate - dob).days > 36500:
        raise CalculationTooWideError(refdate)

    # retrieve or build the extrapolation table for this (sex, region) tuple
    table = dataStore[sex, region]

    # do the calculations
    rank = _calculateRankByDate(table, dob, refdate)
    return long(rank*1000)

# FIXME: this function seems very inefficient. It finds a date based on a rank, but in order to do that it
# searches first by decade (10 calls to _calculateRankByDate) then by year (10 more calls) then interpolates
# linearly (at least that's quick). _calculateRankByDate is itself slow (it does not cache dayInterpA results),
# so this function is 20 x slow.
def dateByWorldPopulationRank(sex, region, dob, rank):
    """
    finding the date for specific rank

    :param birth:
    :param wRank:
    :return:
    """
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(sex, basestring) or not isinstance(region, basestring) or not isinstance(dob, date):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if sex not in SEXES:
        raise InvalidSexError(sex)
    if region not in dataStore.countries:
        raise InvalidCountryError(region)

    # check the various date requirements
    if dob < date(1920, 1, 1) or dob > date(2079, 12, 31):   # the end date has been chosen arbitrarily and is probably wrong
        raise BirthdateOutOfRangeError(dob, 'between 1920-01-01 and 2079-12-31')

    # internally, the algorithm works with k-ranks
    rank = rank / 1000.0

    # prefetch the extrapolation table
    table = dataStore[sex, region]

    # The number of years from input birth to '2100/01/01'
    length_time = relativedelta(date(2100, 1, 1), dob).years

    # Make sure that difference between DOB and final Date < 100
    l_max = min(int(np.floor(length_time/10)*10), 100) # number of years (floor full decades) between dob and 2100

    xx = []
    for jj in range(1, (len(range(10, l_max+10, 10))+1)): # iterates over decades between dob and 2100
        try:
            xx.append(_calculateRankByDate(table, dob, dob + relativedelta(days = jj*3650)))
        except Exception:
            # Breaks the function if either the birthdate is too late for some rank or the rank is too high for some birthdate
            raise DataOutOfRangeError(detail='The input data is out of range: the birthdate is too late for the rank or the rank is too high for the birthdate')

    # check the array for NaN?
    xx = np.array(xx) # convert xx from list to array
    #nanIndex = np.where(np.isnan(xx)) # return array of index positions for NANs

    ''' NEED TO BREAK THE FUNCTION IF CC IS TRUE - NOT YET IMPLEMENTED '''
    # check to see if all of the Ranks are less than the wRank
    if np.all(xx < rank):
        raise DataOutOfRangeError(detail='The input data is out of range: the person is too young')

    #print xx
    # now find the interval containing wRank
    #print rank
    #print np.amin(np.where((xx < rank) == False))
    Upper_bound = (np.amin(np.where((xx < rank) == False))+1)*10 # +1 because of zero index
    Lower_bound = Upper_bound-10

    if xx[1] > rank:
        Lower_bound = 2

    if Lower_bound < 2:
        # I don't know what this error means, but if Lower_bound is < 2, then range_2 will start with a value < 0
        # which means _calculateRankByDate() will be called with a negative age, and that will fail
        raise DataOutOfRangeError()

    # Define new range
    range_2 = np.arange(Lower_bound-2, Upper_bound+1) # +1 due to zero index

    # locate the interval
    xx_ = np.zeros((len(range_2),2))

    # given that interval, do a yearly interpolation
    #print range_2
    for kk in range_2:
        #print kk
        xx_[(kk - np.amin(range_2)),0] = _calculateRankByDate(table, dob, dob + relativedelta(years=kk))
        xx_[(kk - np.amin(range_2)),1] = kk*365

    # Search again for the yearly interval containing wRank
    if xx_[1,0] > rank:
        Lower_bound = 0
        Upper_bound = xx_[-1,1]
    else:
        Upper_bound = xx_[np.amin(np.where((xx_[:,0] < rank) == False)),1]
        Lower_bound = xx_[np.amax(np.where((xx_[:,0] < rank) == True)),1]

    range_3 = np.arange(Lower_bound, Upper_bound+1)
    #print (range_3)

    #xx_ = np.zeros((len(range_3),2))

    # From this point on, this stuff is within a year (daily), due to the fact that the evolution of the rank is linear
    # we do linear interpolation to get the exact day faster
    end_point = range_3[len(range_3)-1]
    first_point = range_3[0]
    # print end_point, first_point

    # Get the rank for the first and last days in range_3
    rank_end = _calculateRankByDate(table, dob, dob + relativedelta(days=end_point))
    rank_first = _calculateRankByDate(table, dob, dob + relativedelta(days=first_point))

    # This gives us the age when we reach wRank and the exact date
    final_age = np.interp(rank, [rank_first, rank_end], [Lower_bound, Upper_bound])
    final_date = dob + relativedelta(days=final_age)
    #print final_age, final_date

    ''' CHECK THESE INTERPOLATION VALUES '''
    #now we also want to plot our life-path, so we do spline interpolation for the stuff we calculated in the first step
    # (i.e. the ranks over decades) and interpolate using bSplines.
    #xx_interp = InterpolatedUnivariateSpline((np.arange(10, l_max+1, 10)*365),xx)
    # print xx_interp
    #x_interp = xx_interp((np.arange(1,36501,365)))
    # print x_interp

    # find the rank nearest to wRank
    #find_r = np.amin(np.where(abs(x_interp - rank)))
    # print find_r

    # The value this function returns
    #exactAge = round(final_age/365, 1)
    #age = math.floor(final_age/365)
    #DATE = final_date

    #pd.DataFrame({'exactAge': pd.Series([exactAge], index = ['1']), 'age': pd.Series([age],index = ['1']), 'DATE': pd.Series([DATE], index = ['1'])})
    return final_date