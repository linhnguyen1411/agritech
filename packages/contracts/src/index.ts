export { default as FarmTokenABI } from '../abis/FarmToken.json';

export interface ContractAddresses {
  FarmToken: string;
}

export const CONTRACT_ADDRESSES: Record<string, ContractAddresses> = {
  '1': {
    FarmToken: '0x0000000000000000000000000000000000000000',
  },
  '31337': {
    FarmToken: '0x5FbDB2315678afecb367f032d93F642f64180aa3',
  },
};
