function outputFile = create_sminst_QSwitch(outputFile)
% create_sminst_QSwitch  Create the legacy Special Measure QSwitch definition.
%
% Run once from MATLAB if sminst_QSwitch.mat is not present:
%   create_sminst_QSwitch
% Start the Python controller first, then load this instrument with:
%   ind = smloadinst('QSwitch', [], 'none');
% Change inst.data.controller_url below if the controller is not local.
% The command selectors are not ordinary smset/smget channels because those
% APIs expect scalar/vector values, not an N-by-2 relay-address matrix.
% Use the backend convention directly, for example:
%   smdata.inst(ind).cntrlfn([ind 1 1], [12 3]);
%
% The COM port is deliberately not stored here.  smloadinst's serial
% override supplies it at setup time.

if nargin < 1 || isempty(outputFile)
    outputFile = fullfile(fileparts(mfilename('fullpath')), 'sminst_QSwitch.mat');
end

inst.device = 'QSwitch';
inst.name = 'QSwitch';
inst.type = zeros(1, 6);
inst.channels = char('OPEN', 'CLOSE', 'STATE', 'IDENTITY', 'ERROR', 'RESET');
inst.cntrlfn = @smcQSwitch;
inst.data = struct('controller_url', 'http://127.0.0.1:8765');
constructor = [];
inst.datadim = zeros(6,1);

save(outputFile, 'inst', 'constructor');
end
