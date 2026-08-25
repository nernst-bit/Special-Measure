function val = smcQSwitch(ic, val, rate)
% smcQSwitch  Minimal USB-serial driver for the QDevil / Quantum Machines QSwitch.
%
% The backend intentionally exposes generic command channels rather than a
% 24-by-8 GUI abstraction.  Direct calls use an N-by-2 numeric relay list:
%   [signal_line breakout]
% where signal_line is 1..24 and breakout is 0..9.  For example,
%   smcQSwitch([inst 1 1], [12 3]) opens (@12!3), and
%   smcQSwitch([inst 2 1], [12 3; 13 0]) closes both relays.
%
% Backend selector channels (not ordinary smset/smget value channels):
%   1 OPEN       write relay list
%   2 CLOSE      write relay list
%   3 STATE      read CLOSE:STATE?
%   4 IDENTITY   read *IDN?
%   5 ERROR      read SYST:ERR:ALL?
%   6 RESET      write *RST
%
% OPEN, CLOSE, and RESET send the command immediately followed by *OPC?.
% The manual permits this synchronization form instead of the 75 ms delay
% between ordinary commands.  Relay switching must still be performed at
% zero applied voltage by the caller.

global smdata;

if numel(ic) < 3 || any(~isfinite(ic(1:3))) || any(ic(1:3) ~= fix(ic(1:3)))
    error('smcQSwitch:InvalidChannel', 'ic must contain integer instrument, channel, and operation indices.');
end

inst = smdata.inst(ic(1)).data.inst;
channel = ic(2);
operation = ic(3); % 0 = read, 1 = write, 2 = ramp/read-buffer (unsupported)

switch channel
    case 1 % OPEN
        require_write(operation, 'OPEN');
        relayText = relay_list(val);
        write_and_wait(inst, sprintf('OPEN %s', relayText));
    case 2 % CLOSE
        require_write(operation, 'CLOSE');
        relayText = relay_list(val);
        command = sprintf('CLOSE %s', relayText);
        validate_command_length(command);
        enforce_bnc_limit(inst, val);
        write_and_wait(inst, command);
    case 3 % CLOSE:STATE?
        require_read(operation, 'CLOSE:STATE?');
        val = read_query(inst, 'CLOSE:STATE?');
    case 4 % *IDN?
        require_read(operation, '*IDN?');
        val = read_query(inst, '*IDN?');
    case 5 % SYST:ERR:ALL?
        require_read(operation, 'SYST:ERR:ALL?');
        val = read_query(inst, 'SYST:ERR:ALL?');
    case 6 % *RST
        require_write(operation, '*RST');
        write_and_wait(inst, '*RST');
    otherwise
        error('smcQSwitch:InvalidChannel', 'Unsupported QSwitch channel %d.', channel);
end

if nargin >= 3 && ~isempty(rate) && channel <= 6 %#ok<INUSD>
    % QSwitch operations are discrete; rate is accepted for SM compatibility.
end

    function require_read(op, name)
        if op ~= 0
            error('smcQSwitch:OperationNotSupported', '%s is read-only.', name);
        end
    end

    function require_write(op, name)
        if op ~= 1
            error('smcQSwitch:OperationNotSupported', '%s is write-only.', name);
        end
    end

    function write_and_wait(serialObject, command)
        validate_command_length(command);
        fprintf(serialObject, command);
        query(serialObject, '*OPC?', '%s\n', '%s');
    end

    function response = read_query(serialObject, command)
        response = query(serialObject, command, '%s\n', '%s');
    end

    function validate_command_length(command)
        % The 127-character limit applies to the SCPI command text.  The
        % serial LF terminator is configured separately and is not included.
        if numel(command) > 127
            error('smcQSwitch:CommandTooLong', ...
                'QSwitch command is %d characters; the maximum is 127 (terminator excluded).', ...
                numel(command));
        end
    end

    function enforce_bnc_limit(serialObject, requested)
        requestedBnc = requested(requested(:, 2) >= 1 & requested(:, 2) <= 8, :);
        if isempty(requestedBnc)
            return;
        end

        stateText = read_query(serialObject, 'CLOSE:STATE?');
        currentState = parse_state(stateText);
        currentBnc = currentState(currentState(:, 2) >= 1 & currentState(:, 2) <= 8, :);
        totalBnc = unique([currentBnc; requestedBnc], 'rows');
        if size(totalBnc, 1) > 40
            error('smcQSwitch:BNCRelayLimit', ...
                'CLOSE would leave %d unique BNC breakout relays closed; the QSwitch limit is 40.', ...
                size(totalBnc, 1));
        end
    end

    function state = parse_state(response)
        % CLOSE:STATE? returns compact SCPI channel-list notation, for
        % example (@1!0:24!0,24!9,23!2).  Only same-breakout line ranges
        % are accepted; an unrecognized response is unsafe for the limit
        % check and therefore aborts the CLOSE before transmission.
        response = strtrim(response);
        outer = regexp(response, '^\(@([0-9!,: ]*)\)$', 'tokens', 'once');
        if isempty(outer)
            error('smcQSwitch:StateParseFailed', ...
                'Cannot safely parse QSwitch CLOSE:STATE? response: %s', response);
        end
        body = strtrim(outer{1});
        if isempty(body)
            state = zeros(0, 2);
            return;
        end

        state = zeros(0, 2);
        entries = strsplit(body, ',');
        for k = 1:numel(entries)
            endpoints = strsplit(strtrim(entries{k}), ':');
            if numel(endpoints) > 2
                error('smcQSwitch:StateParseFailed', ...
                    'Cannot safely parse QSwitch CLOSE:STATE? response: %s', response);
            end
            first = parse_endpoint(endpoints{1}, response);
            last = first;
            if numel(endpoints) == 2
                last = parse_endpoint(endpoints{2}, response);
                if last(2) ~= first(2) || last(1) < first(1)
                    error('smcQSwitch:StateParseFailed', ...
                        'Cannot safely parse QSwitch CLOSE:STATE? response: %s', response);
                end
            end
            state = [state; [(first(1):last(1))' repmat(first(2), last(1) - first(1) + 1, 1)]]; %#ok<AGROW>
        end
        state = unique(state, 'rows');
    end

    function endpoint = parse_endpoint(text, response)
        token = regexp(strtrim(text), '^([0-9]+)!([0-9]+)$', 'tokens', 'once');
        if isempty(token)
            error('smcQSwitch:StateParseFailed', ...
                'Cannot safely parse QSwitch CLOSE:STATE? response: %s', response);
        end
        endpoint = [str2double(token{1}) str2double(token{2})];
        if endpoint(1) < 1 || endpoint(1) > 24 || endpoint(2) < 0 || endpoint(2) > 9
            error('smcQSwitch:StateParseFailed', ...
                'QSwitch CLOSE:STATE? response contains an invalid relay address: %s', response);
        end
    end

    function text = relay_list(addresses)
        if ~isnumeric(addresses) || isempty(addresses) || ndims(addresses) ~= 2 || size(addresses, 2) ~= 2
            error('smcQSwitch:InvalidRelayAddress', ...
                'Relay address must be a nonempty N-by-2 numeric array [signal_line breakout].');
        end
        if any(~isfinite(addresses(:))) || any(addresses(:) ~= fix(addresses(:))) || ...
                any(addresses(:, 1) < 1 | addresses(:, 1) > 24) || ...
                any(addresses(:, 2) < 0 | addresses(:, 2) > 9)
            error('smcQSwitch:InvalidRelayAddress', ...
                'Signal lines must be integers 1..24 and breakout values integers 0..9.');
        end

        parts = cell(size(addresses, 1), 1);
        for n = 1:size(addresses, 1)
            parts{n} = sprintf('%d!%d', addresses(n, 1), addresses(n, 2));
        end
        text = ['(@' join_parts(parts, ',') ')'];
    end

    function text = join_parts(parts, separator)
        text = parts{1};
        for n = 2:numel(parts)
            text = [text separator parts{n}]; %#ok<AGROW>
        end
    end
end
