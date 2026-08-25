function outputFile = create_sminst_QSwitch(outputFile)
% create_sminst_QSwitch  Create the legacy Special Measure QSwitch definition.
%
% Run once from MATLAB if sminst_QSwitch.mat is not present:
%   create_sminst_QSwitch
% Then select the machine-specific port in the demo configuration, e.g.:
%   com = 'COMx';  % replace x on the Windows lab desktop
%   ind = smloadinst('QSwitch', [], 'serial', com);
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
inst.data = struct();

constructor.fn = @serial;
constructor.args = {'Port'};
constructor.params = {'BaudRate', 'DataBits', 'Parity', 'StopBits', 'FlowControl', 'Terminator'};
% Legacy MATLAB serial accepts the canonical named terminator value 'LF',
% which unambiguously selects byte 0x0A rather than a two-character '\n'.
constructor.vals = {9600, 8, 'none', 1, 'none', 'LF'};

save(outputFile, 'inst', 'constructor');
end
