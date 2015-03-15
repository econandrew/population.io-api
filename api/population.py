#from algorithms import *
from dateutil.relativedelta import *
import datetime
import time
import numpy as np

def cmp_relativedelta(rd1, rd2):
    if rd1.years < rd2.years:
        return -1
    elif rd1.years > rd2.years:
        return +1
    elif rd1.months < rd2.months:
        return -1
    elif rd1.months > rd2.months:
        return +1
    elif rd1.days < rd2.days:
        return -1
    elif rd1.days > rd2.days:
        return +1
    else:
        return 0
    
def drange(start, end, step, c=cmp):
    next = start
    while c(next, end) < 0:
        #print "yielding",next, end
        yield next
        next = next + step

class PopulationModel(object):        
    def get_regions(self):
        raise NotImplemented
        
    def get_age_range(self):
        raise NotImplemented
        
    def get_age_quantum(self):
        raise NotImplemented
        
    def get_sexes(self):
        raise NotImplemented
        
    def get_date_range(self):
        raise NotImplemented
        
    def get_date_quantum(self):
        raise NotImplemented

    def get_date_start(self, date):
        raise NotImplemented
        
    def get_date_end(self, date):
        raise NotImplemented
    
    def get_enum_date(self, date):
        raise NotImplemented
               
    def pop_age(self, date, region, sex, age):
        raise NotImplemented
        
    def pop_dob(self, date, region, sex, dob):
        date = self.get_enum_date(date)
        earliest_dob = self.get_date_start(dob)
        latest_dob = self.get_date_end(dob)
        lowest_age = relativedelta(date, latest_dob)
        highest_age = relativedelta(date, earliest_dob)
        # FIXME - this assumes enum_date is always half-way through the date unit (year/month/day)
        return int((self.pop_age(date, region, sex, lowest_age) + self.pop_age(date, region, sex, highest_age))/2)
        
    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None: # zero is a valid value
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
           
        multiage_pop = 0
        for age in drange(age_from, age_to+self.get_age_quantum(), self.get_age_quantum(), cmp_relativedelta):
            multiage_pop += self.pop_age(date, region, sex, age)
            
        return multiage_pop
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        #print date, region, sex, dob_from, dob_to
        age_range = self.get_age_range()
        if dob_from is None: # zero may be a valid value
            dob_from = date - age_range[1]
        if dob_to is None:
            dob_to = date - age_range[0]
            
        multidob_pop = 0
        for dob in drange(dob_from, dob_to+self.get_date_quantum(), self.get_date_quantum()):
            #print self.pop_dob(date, region, sex, dob)
            multidob_pop += self.pop_dob(date, region, sex, dob)
            
        return multidob_pop

    # Find the date when the population born after dob_from is equal to pop
    def pop_integrate_dob_inverse_date(self, pop, region, sex, dob_from):
        date_lower = dob_from
        date_upper = self.get_date_range()[1]
        pop_lower = self.pop_integrate_dob(date_lower, region, sex, dob_from, date_lower)
        pop_upper = self.pop_integrate_dob(date_upper, region, sex, dob_from, date_upper)
        
        def midpoint(lower, upper):
            return lower + (upper - lower) / 2
        
        while cmp_relativedelta(relativedelta(date_upper, date_lower), self.get_date_quantum()):   
            date_midpoint = midpoint(date_lower, date_upper)
            pop_midpoint = self.pop_integrate_dob(date_midpoint, region, sex, dob_from, date_midpoint)
            print 'd',date_lower, date_midpoint, date_upper
            print 'p',pop_lower, pop_midpoint, pop_upper
            if pop_midpoint < pop:
                date_lower, pop_lower = date_midpoint, pop_midpoint
            else:
                date_upper, pop_upper = date_midpoint, pop_midpoint
                
        return date_lower
        
    # date, region, sex can be:
    #  single <group> - return population for that <group>
    #  [<group1>,<group2>,...] - return population for each of those <groups>
    #
    # age, dob can be:
    #  single age - return population for that age
    #  [ages1, age2] - return population for each of those ages
    #  (age_min, age_max) - return population sum for this age range
    def pop(self, date, region, sex, age = None, dob = None):
        if age and dob:
            raise ValueError("must specify exactly one of age, dob")

class MidYearPopulationModel(PopulationModel):    
    def get_age_quantum(self):
        return relativedelta(years=1)
        
    def get_date_quantum(self):
        return relativedelta(years=1)

    def get_date_start(self, date):
        return datetime.date(date.year, 1, 1)
        
    def get_date_end(self, date):
        return datetime.date(date.year, 12, 31)
    
    def get_enum_date(self, date):
        return datetime.date(date.year, 6, 30)
              
import csv
import os.path
import cPickle as pickle
from collections import defaultdict
class NpSingleYearPopulationModel(MidYearPopulationModel):
    def _age_index(self,age):
        return (age-self.age_range[0]).years
        
    def _date_index(self,date):
        return relativedelta(date, self.date_range[0]).years

    def __init__(self, filename, check_or_create_pickle = False):
        self.age_range = (relativedelta(years=0), relativedelta(years=100))
        self.date_range = (self.get_enum_date(datetime.date(1950,1,1)),self.get_enum_date(datetime.date(2100,1,1)))
        self.sexes = ('M','F')
        self.arrays = None
        if check_or_create_pickle and os.path.isfile(filename + ".pickle"):
            with open(filename + ".pickle", "rb") as file:
                self.arrays = pickle.load(file)
        else:
            self.load_pop_csv(filename)
            if check_or_create_pickle:
                with open(filename + ".pickle", "wb") as file:
                    pickle.dump(self.arrays, file)
        

    def load_pop_csv(self, filename):
        self.arrays = defaultdict(lambda: defaultdict(lambda: np.empty((
            self._age_index(self.age_range[1])-self._age_index(self.age_range[0])+1,
            self._date_index(self.date_range[1])-self._date_index(self.date_range[0])+1
        ))))

        with open(filename, 'r') as file:
            reader = csv.DictReader(file)
            # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total

            for row in reader:
                loc_dict = self.arrays[row['Location']]
                loc_dict['M'][
                    self._age_index(relativedelta(years=int(row['Age']))),
                    self._date_index(self.get_enum_date(datetime.date(int(row['Time']),1,1)))
                ] = round(float(row['PopMale'])*1000)
                loc_dict['F'][
                    self._age_index(relativedelta(years=int(row['Age']))),
                    self._date_index(self.get_enum_date(datetime.date(int(row['Time']),1,1)))
                ] = round(float(row['PopFemale'])*1000)

        for loc in self.arrays:
            self.arrays[loc] = dict(self.arrays[loc])
        
        self.arrays = dict(self.arrays)
                
    def get_regions(self):
        return self.arrays.keys()
        
    def get_age_range(self):
        return self.age_range
        
    def get_sexes(self):
        return self.sexes
        
    def get_date_range(self):
        return self.date_range
        
    def pop_age(self, date, region, sex, age):
        date = self.get_enum_date(date)
        if cmp_relativedelta(age, self.age_range[0]) < 0 or cmp_relativedelta(age, self.age_range[1]) > 0:
            return 0
        
        pop = self.arrays[region][sex][self._age_index(age),self._date_index(date)]
        return pop
        

DAYS_PER_YEAR = 365.25
EPOCH = datetime.date(1970, 1, 1)

def to_epoch_days(date):
    return (date - EPOCH).days
    
def from_epoch_days(days):
    delta = datetime.timedelta(days = days)
    return EPOCH + delta

def days_to_decimal_year(days):
    date = from_epoch_days(days)
    
    year = date.year
    year_start = datetime.date(year, 1, 1)
    year_start_days = to_epoch_days(year_start)
    year_end = datetime.date(year, 12, 31)
    year_length = (year_end - year_start).days

    frac = (days - year_start_days) / float(year_length) # force float division
    return year, frac

def decimal_year_to_days(year, frac):
    year_start = datetime.date(year, 1, 1)
    year_start_days = to_epoch_days(year_start)
    year_end = datetime.date(year, 12, 31)
    year_length = (year_end - year_start).days

    days = year_start_days + frac * year_length
    return days

class LinearDailyPopulationModel(PopulationModel):        
    def __init__(self, base_model):
            self.base_model = base_model
            
    def get_regions(self):
        return self.base_model.get_regions()
        
    def get_age_range(self):
        min_years, max_years = self.base_model.get_age_range()
        return (int(min_years * DAYS_PER_YEAR), int(max_years * DAYS_PER_YEAR))
        
    def get_sexes(self):
        return self.base_model.get_sexes()
        
    def get_date_range(self):
        min_year, max_year = self.base_model.get_date_range()
        min_days = to_epoch_days(datetime.date(min_year, 7, 1))
        max_days = to_epoch_days(datetime.date(max_year, 7, 1))
        return (min_days, max_days)
    
    def get_midpoint_year_frac(self,date):
        year, frac = days_to_decimal_year(date)
        # Adjust frac since estimates are treated as midpoint
        if frac > 0.5:
            frac = frac - 0.5
        else:
            frac = frac + 0.5
            year = year - 1
        
        return year, frac
        
    def get_age_year_frac(self, age):
        age_years_float = age / DAYS_PER_YEAR
        age_years = int(age_years_float)
        age_frac = age_years_float - age_years
        return age_years, age_frac
    
    def pop_age(self, date, region, sex, age):
        year, frac = self.get_midpoint_year_frac(date)
        age_years, age_frac = self.get_age_year_frac(age)
        
        # Evaluate the four corners of this grid square on the population surface
        low_year_low_age = self.base_model.pop_age(year, region, sex, age_years) / DAYS_PER_YEAR
        low_year_high_age = self.base_model.pop_age(year, region, sex, age_years+1) / DAYS_PER_YEAR
        high_year_low_age = self.base_model.pop_age(year+1, region, sex, age_years) / DAYS_PER_YEAR
        high_year_high_age = self.base_model.pop_age(year+1, region, sex, age_years+1) / DAYS_PER_YEAR
        
        interp_low_age = low_year_low_age + (high_year_low_age - low_year_low_age) * frac
        interp_high_age =  low_year_high_age + (high_year_high_age - low_year_high_age) * frac
        
        interp = interp_low_age + (interp_high_age - interp_low_age) * age_frac
        return round(interp)
        
    def pop_dob(self, date, region, sex, dob):
        year, frac = self.get_midpoint_year_frac(date)
        dob_year, dob_frac = self.get_midpoint_year_frac(dob)
        #print from_epoch_days(date), from_epoch_days(dob)
        #print dob_year, dob_frac

        # Evaluate the four corners of this grid square on the population surface
        low_year_low_dob = self.base_model.pop_dob(year, region, sex, dob_year) / DAYS_PER_YEAR
        low_year_high_dob = self.base_model.pop_dob(year, region, sex, dob_year+1) / DAYS_PER_YEAR
        high_year_low_dob = self.base_model.pop_dob(year+1, region, sex, dob_year) / DAYS_PER_YEAR
        high_year_high_dob = self.base_model.pop_dob(year+1, region, sex, dob_year+1) / DAYS_PER_YEAR
        
        interp_low_dob = low_year_low_dob + (high_year_low_dob - low_year_low_dob) * frac
        interp_high_dob =  low_year_high_dob + (high_year_high_dob - low_year_high_dob) * frac
        
        interp = interp_low_dob + (interp_high_dob - interp_low_dob) * dob_frac
        return round(interp)    

    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if age_from is None:
            age_from = age_range[0]
        if age_to is None:
            age_to = age_range[1]
    
        age_from_years, age_from_frac = self.get_age_year_frac(age_from)
        age_to_years, age_to_frac = self.get_age_year_frac(age_to)
        
        if age_from_frac == 0.0:
            first_part = 0
            second_part_start = age_from_years
        else:
            first_part = PopulationModel.pop_integrate_age(self, date, region, sex, age_from, int((age_from_years + 1) * DAYS_PER_YEAR - 1))
            second_part_start = int((age_from_years + 1) * DAYS_PER_YEAR)
            
        if age_to_years > second_part_start:
            second_part = self.base_model.pop_integrate_age(date, region, sex, second_part_start, age_to_years-1)
        else:
            second_part = 0
        
        if age_to_frac == 0.0:
            third_part = 0
        else:
            third_part = PopulationModel.pop_integrate_age(self, date, region, sex, int(age_to_years * DAYS_PER_YEAR), age_to)
            
        return first_part + second_part + third_part
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_range = self.get_age_range()
        if dob_from is None: # zero may be a valid value
            dob_from = date - age_range[1]
        if dob_to is None:
            dob_to = date - age_range[0]
    
        dob_from_year, dob_from_frac = self.get_midpoint_year_frac(dob_from)
        dob_to_year, dob_to_frac = self.get_midpoint_year_frac(dob_to)        
        
        if dob_from_frac == 0.0:
            first_part = 0
            second_part_start = dob_from_year
        else:
            first_part = PopulationModel.pop_integrate_dob(self, date, region, sex, dob_from, to_epoch_days(datetime.date(dob_from_year + 1,1,1)) - 1)
            second_part_start = dob_from_year + 1
        
        if dob_to_year > second_part_start:
            second_part = self.base_model.pop_integrate_dob(date, region, sex, second_part_start, dob_to_year-1)
        else:
            second_part = 0
        
        if dob_to_frac == 0.0:
            third_part = 0
        else:
            third_part = PopulationModel.pop_integrate_dob(self, date, region, sex, to_epoch_days(datetime.date(dob_to_year + 1,1,1)), dob_to)
        
        return first_part + second_part + third_part
        
import sys 
if __name__ == "__main__":
#    pop = SingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv")
    pop2 = NpSingleYearPopulationModel("../data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv", True)
    #pop_day = LinearDailyPopulationModel(pop2)

    start_time = time.time()
    def elapsed():
        global start_time
        new_time = time.time()
        out = str(round(new_time - start_time,2)) + " s"
        start_time = new_time
        return out

    print pop2.pop_age(datetime.date(2014,1,1), "Australia", "M", relativedelta(years=2))
    print pop2.pop_integrate_age(datetime.date(2014,1,1), "Australia", "M"), elapsed()
    print pop2.pop_integrate_age(datetime.date(2014,1,1), "Australia", "M", relativedelta(years=10), relativedelta(years=19))
    print pop2.pop_integrate_dob(datetime.date(2014,1,1), "Australia", "M")
    print pop2.pop_integrate_dob_inverse_date(3000000000, "World", "M", datetime.date(1981,1,1)), elapsed()

    #print pop_day.pop_integrate_age(2014, "Australia", "M"), elapsed()
    
    #print pop_day.pop_integrate_age(2014, "Australia", "M", int(2.5*DAYS_PER_YEAR), int(10*DAYS_PER_YEAR))
    #print PopulationModel.pop_integrate_age(pop_day, 2014, "Australia", "M", int(2.5*DAYS_PER_YEAR), int(10*DAYS_PER_YEAR))

    #print pop2.pop_integrate_age(2014, "Australia", "M", 0, 0), elapsed()
    #print pop_day.pop_integrate_age(to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", int(0*DAYS_PER_YEAR), int(1*DAYS_PER_YEAR)), elapsed()
    #print PopulationModel.pop_integrate_age(pop_day, to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", int(0*DAYS_PER_YEAR), int(1*DAYS_PER_YEAR)), elapsed()
    #print sum(pop_day.pop_age(to_epoch_days(datetime.date(2014,7,1)), "Australia", "M", age) for age in range(0,365))

    #print pop2.pop_integrate_dob(2014, "Australia", "M"), elapsed()
    #print PopulationModel.pop_integrate_dob(pop_day, to_epoch_days(datetime.date(2014,7,1)), "Australia", "M"), elapsed()
    #print pop_day.pop_integrate_dob(to_epoch_days(datetime.date(2014,7,1)), "Australia", "M"), elapsed()
    
    #sys.exit(0)
    #print pop_day.pop_age(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", 19*365.25), elapsed() 
    #print pop_day.pop_dob(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()
    #print PopulationModel.pop_dob(pop_day, to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()

    #print pop2.pop_integrate_dob_inverse_date(3000000000, "World", "M", 1981), elapsed()
    #print from_epoch_days(pop_day.pop_integrate_dob_inverse_date(3000000000, "World", "M", to_epoch_days(datetime.date(1981,1,1)))), elapsed()

    #print pop.pop_dob(2010, "Australia", "M", 1981)
    #print pop.pop_integrate_age(2014, "Australia", "M")
    #print PopulationModel.pop_integrate_age(pop,2014, "Australia", "M")