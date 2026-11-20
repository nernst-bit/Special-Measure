function outputFile = create_sminst_QSwitch(outputFile, configFile, controllerUrl, groupId)
% create_sminst_QSwitch  Create the legacy Special Measure QSwitch definition.
%
% Run once from MATLAB if sminst_QSwitch.mat is not present:
%   create_sminst_QSwitch
% Start the Python controller first, then load this instrument with:
%   ind = smloadinst('QSwitch', [], 'none');
% By default, the controller URL is read from the sibling QSwitch-Control checkout. Pass a
% second argument to use a deployed copy of that configuration file.
% The command selectors are not ordinary smset/smget channels because those
% APIs expect scalar/vector values, not an N-by-2 relay-address matrix.
% Use the backend convention directly, for example:
%   smdata.inst(ind).cntrlfn([ind 1 1], [12 3]);
%
% The COM port is deliberately not stored here. The Python controller owns
% the serial connection; Special Measure uses the controller URL in inst.data.

if nargin < 1 || isempty(outputFile)
    outputFile = fullfile(fileparts(mfilename('fullpath')), 'sminst_QSwitch.mat');
end
if nargin < 2 || isempty(configFile)
    repoRoot = fileparts(fileparts(mfilename('fullpath')));
    configFile = fullfile(fileparts(repoRoot), 'QSwitch-Control', 'qswitch_gui', 'config.ini');
end
if nargin < 3 || isempty(controllerUrl)
    controllerUrl = read_controller_url(configFile);
end
if nargin < 4 || isempty(groupId), groupId = 'default'; end

inst.device = 'QSwitch';
inst.name = 'QSwitch';
inst.type = zeros(1, 10);
inst.channels = char('OPEN', 'CLOSE', 'STATE', 'IDENTITY', 'ERROR', 'RESET', ...
    'ACQUIRE', 'RELEASE', 'CONFIGS', 'RESTORE');
inst.cntrlfn = @smcQSwitch;
inst.data = struct('controller_url', controllerUrl, 'group_id', groupId, 'ownership_token', '');
constructor = [];
inst.datadim = zeros(10,1);

save(outputFile, 'inst', 'constructor');
end

function controllerUrl = read_controller_url(configFile)
if ~isfile(configFile)
    error('create_sminst_QSwitch:Configuration', ...
        'QSwitch configuration file not found: %s', configFile);
end
contents = fileread(configFile);
match = regexp(contents, '(?m)^[ \t]*controller_url[ \t]*=[ \t]*([^\r\n#;]+)', 'tokens', 'once');
if isempty(match)
    error('create_sminst_QSwitch:Configuration', ...
        'Global.Controller.controller_url is missing from %s', configFile);
end
controllerUrl = strtrim(match{1});
if isempty(controllerUrl)
    error('create_sminst_QSwitch:Configuration', ...
        'Global.Controller.controller_url is empty in %s', configFile);
end
end
