function data = withQSwitchScanOwnership(qswitchIndex, scan, filename)
% Run the complete blocking Special Measure smrun call under group ownership.
% Covers normal return, scan Escape return, MATLAB exceptions, and Ctrl+C.
global smdata;
if nargin < 3, filename = []; end
smdata.inst(qswitchIndex).cntrlfn([qswitchIndex 7 1], []);
cleanup = onCleanup(@() release_if_owned(qswitchIndex)); %#ok<NASGU>
if isempty(filename)
    data = smrun(scan);
else
    data = smrun(scan, filename);
end
end

function release_if_owned(qswitchIndex)
global smdata;
try
    smdata.inst(qswitchIndex).cntrlfn([qswitchIndex 8 1], []);
catch exception
    warning('withQSwitchScanOwnership:ReleaseFailed', ...
        'QSwitch ownership release failed; operator recovery may be required: %s', exception.message);
end
end
