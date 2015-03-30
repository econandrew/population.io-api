''' 
R to python: yourRank.r
'''
import math
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

import numpy as np
import pandas as pd
from scipy.interpolate import InterpolatedUnivariateSpline

from exceptions import *
from datastore import dataStore
import population

from utils import relativedelta_to_decimal_years

from django.conf import settings

pop_year = population.NpSingleYearPopulationModel(settings.CSV_POPULATION_PATH, check_or_create_pickle=True)
pop_day = population.BicubicSplineDailyPopulationModel(pop_year)

SEXES = {'male': 'M', 'female': 'F', 'unisex': 'All',}

### These are now only used by the life expectency functions and not the population module
###
SEXES_LIFE_EXPECTANCY = {'male': 1, 'female': 2,}

POSIX_EPOCH = date(1970, 1, 1)
def inPosixDays(date):
    """
    Transforms a datetime object into 'posix days', here defined as the days since the posix epoch, Jan 1, 1970.

    :param date: a datetime object
    :return: the corresponding 'posix days' to the given datetime object
    """
    return (date - POSIX_EPOCH).days
###
### 

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

    return pop_day.pop_sum_dob(
        population.to_epoch_days(refdate),
        region,
        SEXES[sex],
        dob_from = population.to_epoch_days(dob),
        dob_to = population.to_epoch_days(refdate)
    )

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

    return population.from_epoch_days(pop_day.pop_sum_dob_inverse_date(rank, region, SEXES[sex], population.to_epoch_days(dob)))

def lifeExpectancyRemaining(sex, region, refdate, age):
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(sex, basestring) or not isinstance(region, basestring) or not isinstance(refdate, date) or not isinstance(age, relativedelta):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if sex not in SEXES_LIFE_EXPECTANCY:
        raise InvalidSexError(sex)
    if region not in dataStore.countries:
        raise InvalidCountryError(region)

    # check the various date requirements
    if refdate < date(1955, 1, 1) or refdate >= date(2095, 1, 1):
        raise CalculationDateOutOfRangeError(refdate, 'from 1955-01-01 to 2094-12-31')
    age_float = relativedelta_to_decimal_years(age)
    if age_float > 120:
        raise AgeOutOfRangeError(age)
    if refdate - age > date(2015, 6, 30):
        raise EffectiveBirthdateOutOfRangeError(invalidValue=(refdate-age))

    # find beginning of 5 yearly period for the le_date
    le_yr = refdate.year
    lowest_year = math.floor(int(le_yr)/5)*5

    # extract a row corresponding to the time-period
    life_exp_prd_5below = dataStore.life_expectancy_ages[(dataStore.life_expectancy_ages.region == region) & (dataStore.life_expectancy_ages.sex == SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.life_expectancy_ages.Begin_prd == lowest_year-5)]
    life_exp_prd_ext = dataStore.life_expectancy_ages[(dataStore.life_expectancy_ages.region == region) & (dataStore.life_expectancy_ages.sex == SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.life_expectancy_ages.Begin_prd == lowest_year)]
    life_exp_prd_5above = dataStore.life_expectancy_ages[(dataStore.life_expectancy_ages.region == region) & (dataStore.life_expectancy_ages.sex == SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.life_expectancy_ages.Begin_prd == lowest_year+5)]

    # life_exp_prd
    life_exp_prd = pd.concat([life_exp_prd_5below, life_exp_prd_ext, life_exp_prd_5above])
    life_exp_prd = life_exp_prd.ix[:,4:len(life_exp_prd.columns)]

    # Place holder for Agenames and values for three consecutive periods of interest
    life_exp_ = np.zeros((len(life_exp_prd.columns), 4))

    # Age group starting at and less than the next value: 0, 1, 5, 10
    life_exp_[:,0] = np.insert((np.arange(5, 130, 5)), 0, [0,1])

    # transpose the dataframe - prep for assinging life expectancy vals
    life_exp_prd = life_exp_prd.T

    # Assigning life expectancy values
    life_exp_[:,1] = life_exp_prd[life_exp_prd.columns[0]].values
    life_exp_[:,2] = life_exp_prd[life_exp_prd.columns[1]].values
    life_exp_[:,3] = life_exp_prd[life_exp_prd.columns[2]].values

    # interpolations
    xx_interp1 = InterpolatedUnivariateSpline(life_exp_[:,0],life_exp_[:,1])
    xx_interp2 = InterpolatedUnivariateSpline(life_exp_[:,0],life_exp_[:,2])
    xx_interp3 = InterpolatedUnivariateSpline(life_exp_[:,0],life_exp_[:,3])

    # predictions
    x_interp1 = xx_interp1(age_float)   #interpolated value for AGE in earlier 5 yearly period
    x_interp2 = xx_interp2(age_float)   #interpolated value for AGE in the 5 yearly period of interest
    x_interp3 = xx_interp3(age_float)   #interpolated value for AGE in 5 yearly period after

    # matrix of vals
    life_exp_yr = np.zeros((3,2))

    #The mid point of period 2010-2015 which is from 1st July 2010 to June 30 of 2015, therefore, the mid point is 1st Jan 2013
    #In the following we turn the year to the date and then to numeric. We will use these to interpolate between periods and then predict the le for exact date
    addDate = lambda d: inPosixDays(date(int(d)+3, 1, 1))

    life_exp_yr[:,0] = [addDate(lowest_year-5), addDate(lowest_year), addDate(lowest_year+5)]
    life_exp_yr[:,1] = [x_interp1, x_interp2, x_interp3]

    life_exp_spl = InterpolatedUnivariateSpline(life_exp_yr[:,0], life_exp_yr[:,1], k=2)
    return life_exp_spl(inPosixDays(refdate))[()]

def lifeExpectancyTotal(sex, region, dob):
    if not isinstance(dob, date):
        raise TypeError('One or more arguments did not match the expected parameter type')

    if dob < date(1920, 1, 1) or dob > date(2059, 12, 31):
        raise BirthdateOutOfRangeError(dob, 'between 1920-01-01 and 2059-12-31')

    age = relativedelta(years=35)   # set an arbitrary age that keeps our calculation in the boundaries of lifeExpectancyRemaining()
    age_float = relativedelta_to_decimal_years(age)
    refdate = dob + age
    return age_float + lifeExpectancyRemaining(sex, region, refdate, age)

def populationCount(country, age=None, year=None):
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(country, basestring) or (age is not None and not isinstance(age, int)) or (year is not None and not isinstance(year, int)):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if country not in dataStore.countries:
        raise InvalidCountryError(country)

    # check the various date requirements
    if age is None and year is None:   # note: age can be 0, so we have to check for None here, checking for truthyness is *not* sufficient!
        raise DataOutOfRangeError('Either an age or a year have to be specified')
    if age is not None and (age < 1 or age > 100):   # FIXME: actually, an age of 0 should be valid, but the lookup with Pandas doesn't work for some reason
        raise DataOutOfRangeError('The age %i can not be processed, because only ages between 1 and 100 years are supported' % age)
    if year is not None and (year < 1950 or year > 2100):
        raise DataOutOfRangeError('The year %i can not be processed, because only years between 1950 and 2100 are supported' % year)

    results = []
    for a in [age] if age else pop_year.ages():
        for y in [year] if year else pop_year.dates():
            results.append({
                'year': y,
                'age': a,
                'males': pop_year.pop_age(y, country, 'M', a),
                'females': pop_year.pop_age(y, country, 'F', a),
                'total': pop_year.pop_age(y, country, 'All', a)
            })
    return results

def totalPopulation(country, refdate):
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(country, basestring) or (not isinstance(refdate, date)):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if country not in dataStore.countries:
        raise InvalidCountryError(country)

    # check the various date requirements
    if refdate < date(2013, 1, 1) or refdate > date(2022, 12, 31):
        raise CalculationDateOutOfRangeError(refdate, 'between 2013-01-01 and 2022-12-31')

    return pop_day.pop_sum_age(population.to_epoch_days(refdate), country, 'All')

def continentBirthsByDate(continent, refdate):
    pass
#     # check that all arguments have the right type (even though it's not very pythonic)
#     if not isinstance(continent, basestring) or (not isinstance(refdate, date)):
#         raise TypeError('One or more arguments did not match the expected parameter type')
#
#     # confirm that sex and region contain valid values
#     if continent not in dataStore.continent_countries:
#         raise InvalidContinentError(continent)
#
#     # check the various date requirements
#     if refdate < date(1950, 1, 1) or refdate > date(2100, 12, 31):
#         raise CalculationDateOutOfRangeError(refdate, 'between 1950-01-01 and 2100-12-31')
#
#     refdateAsShortDateString = refdate.strftime('%y/%m/%d')
#
#     cntrys = dataStore.continent_countries.loc[Continent==continent,'POPIO_NAME']
#
#     #Population aged 0 at DATE
#     births1 = dataStore.births_day_country.loc[refdateAsShortDateString,cntrys]
#     #Population aged 0 at DATE+1
#     births2 = dataStore.births_day_country.loc[refdateAsShortDateString+1,cntrys]
#
#     births_on_day = births2-births1
#     births_on_day[births_on_day<0] = 0
#
#     return list(births_on_day)

def calculateMortalityDistribution(country, sex, age):
    # check that all arguments have the right type (even though it's not very pythonic)
    if not isinstance(sex, basestring) or not isinstance(country, basestring) or not isinstance(age, relativedelta):
        raise TypeError('One or more arguments did not match the expected parameter type')

    # confirm that sex and region contain valid values
    if sex not in SEXES_LIFE_EXPECTANCY:
        raise InvalidSexError(sex)
    if country not in dataStore.countries:
        raise InvalidCountryError(country)
    age_float = relativedelta_to_decimal_years(age)
    if age_float > 120:
        raise AgeOutOfRangeError(age)

    # helper function
    def setInterpDate(x, offset):
        """ ??? """
        idate = datetime.strptime(str(x+offset+3)+"/1"+"/1", "%Y/%m/%d")
        return (idate - datetime(1970, 1, 1)).days
    def rounddown(x, base=5):
        return int(base * math.floor(float(x)/base))

    # get columns which correspond to the inputs
    idate = datetime.utcnow().date()
    iage = age_float
    iyear = idate.year
    flr_yr = rounddown(iyear, base=5)

    # get closest age in 5 year windows
    flr_age = rounddown(iage, base=5)

    # Get the age cohort
    if flr_age >= 5:
        cohort_st = list(dataStore.survival_ratio.columns).index("X"+str(flr_age-5))
    else:
        cohort_st = 4
    cohort_end = len(dataStore.survival_ratio.columns)
    #cohort = dataStore.survival_ratio.loc[(dataStore.survival_ratio.region==country) & (dataStore.survival_ratio.sex==SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.survival_ratio.Begin_prd >=(flr_yr-5))].ix[:,cohort_st:cohort_end]

    # get older and younger cohort
    cohort_old = dataStore.survival_ratio.loc[(dataStore.survival_ratio.region==country) & (dataStore.survival_ratio.sex==SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.survival_ratio.Begin_prd >=(flr_yr-10))].ix[:,cohort_st:cohort_end]
    #cohort_young = dataStore.survival_ratio.loc[(dataStore.survival_ratio.region==country) & (dataStore.survival_ratio.sex==SEXES_LIFE_EXPECTANCY[sex]) & (dataStore.survival_ratio.Begin_prd >=(flr_yr))].ix[:,cohort_st:cohort_end]

    # get dates for the jan 1st for 3 years --> then to Unix timestamp
    dates = [setInterpDate(flr_yr, -5), setInterpDate(flr_yr, 0), setInterpDate(flr_yr, +5)]

    # make the output dataStore.survival_ratiotable
    temp = np.zeros(shape=(len(cohort_old.columns),7))
    odata = pd.DataFrame(temp, columns=["lower_age","pr0","pr1","pr2","pr_sx_date","death_percent","dth_pc_after_exact_age"])

    # fill in with existing values
    if iage>=5:
        odata['lower_age'] = np.arange(flr_age-5, 130, 5)
    else:
        odata['lower_age'] = np.arange(0, 130, 5)
    odata['pr0'] = np.matrix(cohort_old).diagonal().T
    odata['pr1'] = np.matrix(cohort_old).diagonal(-1).T
    odata['pr2'] = np.matrix(cohort_old).diagonal(-2).T

    # Interpolate for the input date (idate)
    odata["pr_sx_date"] = np.array([InterpolatedUnivariateSpline(dates,list(odata.ix[i,1:4]),k=2)(inPosixDays(idate)) for i in np.arange(0, len(cohort_old.columns),1)])

    clen = len(odata)
    # calc the % deaths
    odata["death_percent"][1] = 100
    for i in np.arange(2,clen,1):
        odata["death_percent"][i] = odata["death_percent"][i-1]*odata["pr_sx_date"][i]

    # percentage deaths
    for i in np.arange(1,clen-1,1):
        odata["dth_pc_after_exact_age"][i] = odata["death_percent"][i] - odata["death_percent"][i+1]

    odata["dth_pc_after_exact_age"][clen-1] = odata["death_percent"][clen-1]

    # proportion of people who will die before iage
    beforeDod = odata["dth_pc_after_exact_age"][1] * (iage - flr_age)/5
    odata["dth_pc_after_exact_age"][1] = odata["dth_pc_after_exact_age"][1] - beforeDod
    odata["dth_pc_after_exact_age"] = odata["dth_pc_after_exact_age"]* 100/odata["dth_pc_after_exact_age"].sum()

    # add 5 to each of the "ages"
    if iage>=5:
        odata["lower_age"] = odata["lower_age"]+5
    else:
        odata["lower_age"] = odata["lower_age"]+iage

    output = odata.ix[0:clen-1,['lower_age', 'dth_pc_after_exact_age']]
    return list(output.values)
