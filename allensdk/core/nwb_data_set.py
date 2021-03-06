# Copyright 2015 Allen Institute for Brain Science
# This file is part of Allen SDK.
#
# Allen SDK is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.
#
# Allen SDK is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# Merchantability Or Fitness FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Allen SDK.  If not, see <http://www.gnu.org/licenses/>.

import h5py
import numpy as np

class NwbDataSet(object):
    """ A very simple interface for exracting electrophysiology data
    from an NWB file.
    """

    def __init__(self, file_name):
        """ Initialize the NwbDataSet instance with a file name

        Parameters
        ----------
        file_name: string
           NWB file name
        """
        self.file_name = file_name
    
    def get_sweep(self, sweep_number):
        """ Retrieve the stimulus, response, index_range, and sampling rate
        for a particular sweep.  This method hides the NWB file's distinction 
        between a "Sweep" and an "Experiment".  An experiment is a subset of
        of a sweep that excludes the initial test pulse.  It also excludes 
        any erroneous response data at the end of the sweep (usually for
        ramp sweeps, where recording was terminated mid-stimulus).  

        Some sweeps do not have an experiment, so full data arrays are 
        returned.  Sweeps that have an experiment return full data arrays
        (include the test pulse) with any erroneous data trimmed from the 
        back of the sweep.  

        Parameters
        ----------
        sweep_number: int

        Returns
        -------
        dict
            A dictionary with 'stimulus', 'response', 'index_range', and
            'sampling_rate' elements.  The index range is a 2-tuple where
            the first element indicates the end of the test pulse and the
            second index is the end of valid response data.
        """
        with h5py.File(self.file_name,'r') as f:
            
            swp = f['epochs']['Sweep_%d' % sweep_number]
            
            stimulus = swp['stimulus']['timeseries']['data'].value
            response = swp['response']['timeseries']['data'].value
            
            swp_idx_start = swp['stimulus']['idx_start'].value
            swp_length = swp['stimulus']['count'].value

            swp_idx_stop = swp_idx_start + swp_length - 1
            sweep_index_range = ( swp_idx_start, swp_idx_stop )

            # if the sweep has an experiment, extract the experiment's index range
            try:
                exp = f['epochs']['Experiment_%d' % sweep_number]
                exp_idx_start = exp['stimulus']['idx_start'].value
                exp_length = exp['stimulus']['count'].value
                exp_idx_stop = exp_idx_start + exp_length - 1
                experiment_index_range = ( exp_idx_start, exp_idx_stop )
            except KeyError, _:
                # this sweep has no experiment.  return the index range of the entire sweep.
                experiment_index_range = sweep_index_range
            
            assert sweep_index_range[0] == 0, Exception("index range of the full sweep does not start at 0.")
            
            # only return data up to the end of the experiment -- ignore everything else
            return  {
                'stimulus': stimulus[sweep_index_range[0]:experiment_index_range[1]+1],
                'response': response[sweep_index_range[0]:experiment_index_range[1]+1],
                'index_range': experiment_index_range,
                'sampling_rate': 1.0 * swp['stimulus']['timeseries']['starting_time'].attrs['rate']
            }
    
    
    def set_sweep(self, sweep_number, stimulus, response):
        """ Overwrite the stimulus or response of an NWB file.  
        If the supplied arrays are shorter than stored arrays,
        they are padded with zeros to match the original data 
        size.

        Parameters
        ----------
        sweep_number: int

        stimulus: np.array
           Overwrite the stimulus with this array.  If None, stimulus is unchanged.

        response: np.array
            Overwrite the response with this array.  If None, response is unchanged.
        """

        with h5py.File(self.file_name,'r+') as f:
            swp = f['epochs']['Sweep_%d' % sweep_number]
            
            # this is the length of the entire sweep data, including test pulse and 
            # whatever might be in front of it
            # TODO: remove deprecated 'idx_stop'
            if 'idx_stop' in swp['stimulus']:
                sweep_length = swp['stimulus']['idx_stop'].value + 1
            else:
                sweep_length = swp['stimulus']['count'].value
            
            if stimulus is not None:
                # if the data is shorter than the sweep, pad it with zeros
                missing_data = sweep_length - len(stimulus)
                if missing_data > 0:
                    stimulus = np.append(stimulus, np.zeros(missing_data))
                
                swp['stimulus']['timeseries']['data'][...] = stimulus
            
            if response is not None:
                # if the data is shorter than the sweep, pad it with zeros
                missing_data = sweep_length - len(response)
                if missing_data > 0:
                    response = np.append(response, np.zeros(missing_data))
                
                
                swp['response']['timeseries']['data'][...] = response
    

    def get_spike_times(self, sweep_number):
        """ Return any spike times stored in the NWB file for a sweep.

        Parameters
        ----------
        sweep_number: int

        Returns
        -------
        list
           list of spike times in seconds relative to the start of the sweep
        """
        with h5py.File(self.file_name,'r') as f:
            sweep_name = "Sweep_%d" % sweep_number
            
            try:
                spikes = f["analysis"]["aibs_spike_times"][sweep_name]
            except KeyError:
                return []
            
            return spikes.value
    
    
    def set_spike_times(self, sweep_number, spike_times):
        """ Set or overwrite the spikes times for a sweep.
        
        Parameters
        ----------
        sweep_number: int
        
        spike_times: np.array
           array of spike times in seconds
        """
        with h5py.File(self.file_name,'r+') as f:
            # make sure expected directory structure is in place
            if "analysis" not in f.keys():
                f.create_group("analysis")
            
            analysis_dir = f["analysis"]
            if "aibs_spike_times" not in analysis_dir.keys():
                analysis_dir.create_group("aibs_spike_times")
            
            spike_dir = analysis_dir["aibs_spike_times"]
            
            # see if desired dataset already exists
            sweep_name = "Sweep_%d" % sweep_number
            if sweep_name in spike_dir.keys():
                # rewriting data -- delete old dataset
                del spike_dir[sweep_name]
            
            spike_dir.create_dataset(sweep_name, data=spike_times, dtype='f8')


    def get_sweep_numbers(self):
        """ Get all of the sweep numbers in the file, including test sweeps. """
        
        with h5py.File(self.file_name, 'r') as f:
            sweeps = [int(e.split('_')[1]) for e in f['epochs'].keys() if e.startswith('Sweep_')]
            return sweeps


    def get_experiment_sweep_numbers(self):
        """ Get all of the sweep numbers for experiment epochs in the file, not including test sweeps. """
        
        with h5py.File(self.file_name, 'r') as f:
            sweeps = [int(e.split('_')[1]) for e in f['epochs'].keys() if e.startswith('Experiment_')]
            return sweeps
        

    def fill_sweep_responses(self, fill_value=0.0, sweep_numbers=None):
        """ Fill sweep response arrays with a single value.

        Parameters
        ----------
        fill_value: float
            Value used to fill sweep response array
        
        sweep_numbers: list
            List of integer sweep numbers to be filled (default all sweeps)
            
        """

        with h5py.File(self.file_name, 'a') as f:
            if sweep_numbers is None:
                # no sweep numbers given, grab all of them
                epochs = [ k for k in f['epochs'].keys() if k.startswith('Sweep_') ]
            else:
                epochs = [ 'Sweep_%d' % sweep_number for sweep_number in sweep_numbers ]

            for epoch in epochs:
                if epoch in f['epochs']:
                    f['epochs'][epoch]['response']['timeseries']['data'][...] = fill_value

    def get_sweep_metadata(self, sweep_number):
        """ Retrieve the sweep level metadata associated with each sweep.
        Includes information on stimulus parameters like its name and amplitude 
        as well as recording quality metadata, like access resistance and 
        seal quality.

        Parameters
        ----------
        sweep_number: int

        Returns
        -------
        dict
            A dictionary with 'aibs_stimulus_amplitude_pa', 'aibs_stimulus_name', 
            'gain', 'initial_access_resistance', 'seal' elements.  These specific
            fields are ones encoded in the original AIBS in vitro .nwb files.
        """
        with h5py.File(self.file_name,'r') as f:
            
            sweep_metadata = {}

            # the sweep level metadata is stored in stimulus/presentation/Sweep_XX in the .nwb file

            # indicates which metadata fields to return
            metadata_fields = ['aibs_stimulus_amplitude_pa', 'aibs_stimulus_name', 'gain', 'initial_access_resistance', 'seal']
            try:
                stim_details = f['stimulus']['presentation']['Sweep_%d' % sweep_number]
                for field in metadata_fields:
                	# check if sweep contains the specific metadata field
                	if field in stim_details.keys():
                		sweep_metadata[field] = stim_details[field].value

            except KeyError, _:
                sweep_metadata = {}
            
            return sweep_metadata