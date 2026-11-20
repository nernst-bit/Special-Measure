function result = withQSwitchOwnership(qswitchIndex, sequence)
% Run sequence(qswitchIndex) while holding the configured group lock.
% The callback must issue explicit QSwitch route operations.
global smdata;
if ~isa(sequence, 'function_handle')
    error('withQSwitchOwnership:Callback', 'sequence must be a function handle.');
end
smdata.inst(qswitchIndex).cntrlfn([qswitchIndex 7 1], []);
cleanup = onCleanup(@() release_if_owned(qswitchIndex)); %#ok<NASGU>
result = sequence(qswitchIndex);
end

function release_if_owned(qswitchIndex)
global smdata;
try
    smdata.inst(qswitchIndex).cntrlfn([qswitchIndex 8 1], []);
catch exception
    warning('withQSwitchOwnership:ReleaseFailed', ...
        'QSwitch ownership release failed; operator recovery may be required: %s', exception.message);
end
end
