#from algorithms import *
#from dateutil.relativedelta import *
import datetime
import time

class PopulationModel(object):
    def get_regions(self):
        raise NotImplemented
        
    def get_age_range(self):
        raise NotImplemented
        
    def get_age_quantum(self):
        return 1
        
    def get_sexes(self):
        raise NotImplemented
        
    def get_date_range(self):
        raise NotImplemented
        
    def get_date_quantum(self):
        return 1
    
    def pop_age(self, date, region, sex, age):
        raise NotImplemented
        
    def pop_dob(self, date, region, sex, dob):
        print date, region, sex, dob
        age = date - dob
        return self.pop_age(date, region, sex, age)
        
    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if not age_from:
            age_from = age_range[0]
        if not age_to:
            age_to = age_range[1]
           
        multiage_pop = 0
        for age in range(age_from, age_to+self.get_age_quantum(), self.get_age_quantum()):
            multiage_pop += self.pop_age(date, region, sex, age)
            
        return multiage_pop
        
    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        print date, region, sex, dob_from, dob_to
        age_range = self.get_age_range()
        if not dob_from:
            dob_from = date - age_range[1]
        if not dob_to:
            dob_to = date - age_range[0]
            
        multidob_pop = 0
        for dob in range(dob_from, dob_to+self.get_date_quantum(), self.get_date_quantum()):
            multidob_pop += self.pop_dob(date, region, sex, dob)
            
        return multidob_pop

    # Find the date when the population born after dob_from is equal to pop
    def pop_integrate_dob_inverse_date(self, pop, region, sex, dob_from):
        dob_from = dob_from
        
        date_lower = dob_from
        date_upper = self.get_date_range()[1]
        pop_lower = self.pop_integrate_dob(date_lower, region, sex, dob_from, date_lower)
        pop_upper = self.pop_integrate_dob(date_upper, region, sex, dob_from, date_upper)
        
        def midpoint(lower, upper):
            return lower + (upper - lower) / 2
        
        while date_upper - date_lower > self.get_date_quantum():   
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
                
            
        
class UnitPopulationModel(PopulationModel):
    def get_regions(self):
        return ["Oceania", "Eurasia", "Eastasia"]
        
    def get_age_range(self):
        return (0, 100)
            
    def get_sexes(self):
        return ("M", "F")
        
    def get_date_range(self):
        return (1948, 1984)
        
    def pop_age(self, date, region, sex, age):
        return 1   

import pandas as pd
import numpy as np
class SingleYearPopulationModel(PopulationModel):
    sexmap = {
        'M': 'PopMale',
        'F': 'PopFemale'
    }
    
    def __init__(self, filename):
        # population by single year of age and year from 1950-2100
        # ?, LocID, Location (Country), VarID, Variant, Time, Age, pop male, pop female, pop total
        self.raw = pd.read_csv(filename)
        self.raw.YOB = self.raw.Time - self.raw.Age
    
    def get_regions(self):
        return self.raw.Location.unique()
        
    def get_age_range(self):
        return (self.raw.Age.min(), self.raw.Age.max())
        
    def get_sexes(self):
        return np.array(self.sexmap.keys())
        
    def get_date_range(self):
        return (self.raw.Time.min(), self.raw.Time.max())
        
    def pop_age(self, date, region, sex, age):
        if age < self.get_age_range()[0] or age > self.get_age_range()[1]:
            return 0
        
        return int(np.rint(self.raw[
            (self.raw.Time == date) &
            (self.raw.Location == region) &
            (self.raw.Age == age)
        ].get(SingleYearPopulationModel.sexmap[sex])*1000),)
        
    def pop_integrate_age(self, date, region, sex, age_from = None, age_to = None):
        age_range = self.get_age_range()
        if not age_from:
            age_from = age_range[0]
        if not age_to:
            age_to = age_range[1]
           
        return int(np.rint(self.raw[
            (self.raw.Time == date) &
            (self.raw.Location == region) &
            (self.raw.Age >= age_from) &
            (self.raw.Age <= age_to)
        ].get(SingleYearPopulationModel.sexmap[sex]).sum()*1000))        

    def pop_integrate_dob(self, date, region, sex, dob_from = None, dob_to = None):
        age_range = self.get_age_range()
        date_range = self.get_date_range()
        if not dob_from:
            dob_from = date_range[0] - age_range[1]
        if not dob_to:
            dob_to = date_range[1] - age_range[0]
           
        return int(np.rint(self.raw[
            (self.raw.Time == date) &
            (self.raw.Location == region) &
            (self.raw.YOB >= dob_from) &
            (self.raw.YOB <= dob_to)
        ].get(SingleYearPopulationModel.sexmap[sex]).sum()*1000))        

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
        return (min_years * DAYS_PER_YEAR, max_years * DAYS_PER_YEAR)
        
    def get_sexes(self):
        return self.base_model.get_sexes()
        
    def get_date_range(self):
        min_year, max_year = self.base_model.get_date_range()
        min_days = to_epoch_days(datetime.date(min_year, 1, 1))
        max_days = to_epoch_days(datetime.date(max_year, 12, 31))
        return (min_days, max_days)
        
    def pop_age(self, date, region, sex, age):
        year, frac = days_to_decimal_year(date)
        age_years_float = age / DAYS_PER_YEAR
        age_years = int(age_years_float)
        age_frac = age_years_float - age_years
        
        # Evaluate the former corners of this grid square on the population surface
        low_year_low_age = self.base_model.pop_age(year, region, sex, age_years) / DAYS_PER_YEAR
        low_year_high_age = self.base_model.pop_age(year, region, sex, age_years+1) / DAYS_PER_YEAR
        high_year_low_age = self.base_model.pop_age(year+1, region, sex, age_years) / DAYS_PER_YEAR
        high_year_high_age = self.base_model.pop_age(year+1, region, sex, age_years+1) / DAYS_PER_YEAR
        
        interp_low_age = low_year_low_age + (high_year_low_age - low_year_low_age) * frac
        interp_high_age =  low_year_high_age + (high_year_high_age - low_year_high_age) * frac
        
        interp = interp_low_age + (interp_high_age - interp_low_age) * age_frac
        return round(interp)
        
    def pop_dob(self, date, region, sex, dob):
        year, frac = days_to_decimal_year(date)
        dob_year, dob_frac = days_to_decimal_year(dob)
        
        # Evaluate the former corners of this grid square on the population surface
        low_year_low_dob = self.base_model.pop_dob(year, region, sex, dob_year) / DAYS_PER_YEAR
        low_year_high_dob = self.base_model.pop_dob(year, region, sex, dob_year+1) / DAYS_PER_YEAR
        high_year_low_dob = self.base_model.pop_dob(year+1, region, sex, dob_year) / DAYS_PER_YEAR
        high_year_high_dob = self.base_model.pop_dob(year+1, region, sex, dob_year+1) / DAYS_PER_YEAR
        
        interp_low_dob = low_year_low_dob + (high_year_low_dob - low_year_low_dob) * frac
        interp_high_dob =  low_year_high_dob + (high_year_high_dob - low_year_high_dob) * frac
        
        interp = interp_low_dob + (interp_high_dob - interp_low_dob) * dob_frac
        return round(interp)    
        
if __name__ == "__main__":
    pop = SingleYearPopulationModel("/Users/andrew/Documents/Work/WBG/population.io/population.io-api/data/WPP2012_INT_F3_Population_By_Sex_Annual_Single_100_Medium.csv")
    pop_day = LinearDailyPopulationModel(pop)

    start_time = time.time()
    def elapsed():
        global start_time
        new_time = time.time()
        out = str(round(new_time - start_time,2)) + " s"
        start_time = new_time
        return out

    print pop_day.pop_age(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", 19*365.25), elapsed() 
    print pop.pop_age(2010, "Australia", "M", 19), elapsed()
    print pop.pop_age(2011, "Australia", "M", 19), elapsed()
    print pop_day.pop_dob(to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()
    print PopulationModel.pop_dob(pop_day, to_epoch_days(datetime.date(2010, 6, 15)), "Australia", "M", to_epoch_days(datetime.date(1991, 9, 15))), elapsed()

    print pop.pop_integrate_dob_inverse_date(1000000, "Australia", "M", 1981)
    print pop_day.pop_integrate_dob_inverse_date(1000000, "Australia", "M", to_epoch_days(datetime.date(1981,1,1)))

    #print pop.pop_dob(2010, "Australia", "M", 1981)
    #print pop.pop_integrate_age(2014, "Australia", "M")
    #print PopulationModel.pop_integrate_age(pop,2014, "Australia", "M")
        
    